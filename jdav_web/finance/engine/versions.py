"""Importing, resolving and verifying a version of a section's rules.

The engine never reads rules from a file. It reads them from a
:class:`~finance.store.RuleSet` row, and a statement reads them from its own
copy of that row — which is what lets an old statement keep the rules it was
created under while the configuration repository moves on.

The import is deliberately boring and refuses loudly:

1. read every ``*.py`` under the ruleset's directory,
2. run the import whitelist over them,
3. build the manifest and hash it; a hash that is already stored *is* that
   version, so an import is idempotent and a reformat is a new version,
4. load the sources, which checks that they export a usable ``Ruleset``,
5. run the ruleset's own cases,
6. on success activate the row and close its predecessor's validity; on
   failure store the row as a *draft* with its problems, leave the previous
   version active, and say so loudly.

Step 6's failure behaviour is OPA's: a bad configuration does not take the
instance down, it keeps serving the last good version and complains. The
alternative — refusing to start — turns a typo in a rule into an outage.

Nothing here imports ``finance.models``, because ``finance.models`` imports the
engine. Anything that needs a statement takes one as an argument.
"""

import hashlib
import logging
import os
import platform
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from decimal import InvalidOperation
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from finance.rules_api import Ruleset
from finance.store import RuleSet

from .cases import run_cases
from .context import PARAMETER_KEYS
from .errors import RulesetInvalid
from .errors import RulesetRejected
from .guard import no_queries
from .imports import check_sources
from .loader import load
from .loader import manifest
from .loader import manifest_hash
from .loader import read_sources

logger = logging.getLogger(__name__)

#: Where a ruleset's own cases live inside its package.
CASES_DIRECTORY = "cases"


def engine_version() -> str:
    """What a ruleset was imported into, as text for the record.

    The Kompass version and the interpreter, because a stdlib function that
    changed between interpreters is one of the two things a text hash cannot
    notice. Both come from the environment, which is where the image will put
    them once it carries a version at all (#499); until then this says
    ``unknown`` rather than pretending.
    """
    parts = [
        f"kompass {os.environ.get('KOMPASS_VERSION', '') or 'unknown'}",
        f"{platform.python_implementation()} {platform.python_version()}",
    ]
    digest = os.environ.get("KOMPASS_IMAGE_DIGEST", "")
    if digest:
        parts.append(digest)
    return "; ".join(parts)


def ruleset_directory() -> Path | None:
    """The configured ruleset package, or ``None`` when there is none.

    ``[finance] ruleset`` names a directory under ``KOMPASS_CONFIG_DIR_PATH``,
    the same read-only mount the section's ``settings.toml`` comes from. Unset
    means: use the reference ruleset that ships in the image.
    """
    name = getattr(settings, "FINANCE_RULESET", "")
    if not name:
        return None
    return Path(getattr(settings, "CONFIG_DIR_PATH", "")) / name


def reference_directory() -> Path:
    """The reference ruleset's package inside this repository."""
    return Path(__file__).resolve().parent.parent / "rulesets" / "heidelberg"


def configured_directory() -> Path:
    """The ruleset to import: the section's own, or the reference one."""
    return ruleset_directory() or reference_directory()


def parameters_from_settings() -> dict[str, str]:
    """The section's numbers as a new version's parameters.

    Exact decimal *strings* — not floats, and not integer cents: a rate of
    ``0,155 €`` per kilometre and a tax of ``0,19`` are both configurable today
    and neither is a whole number of cents.

    TOML parses ``0.155`` into a float before this sees it, so the float is not
    avoided — what is avoided is *storing* one and canonicalising it later:
    ``str(float)`` recovers the literal the section wrote, and from there the
    value is text all the way through the hash and the snapshot. Amounts — what
    a rule *produces* — are integer cents, on
    :class:`~finance.store.Obligation`, which is where IEEE-754 would actually
    bite.
    """
    return {key: str(getattr(settings, key, 0)) for key in PARAMETER_KEYS}


def params_fingerprint(params: Mapping[str, Any]) -> str:
    """The parameters as one canonical line per key, for hashing.

    Exact text, sorted, with no JSON in sight: a version's identity has to
    cover its numbers as well as its code, because changing the allowance per
    day changes what a statement resolves to just as surely as changing a rule
    does. It is also why a parameter change is a new row rather than an edit —
    the hash moves, and nothing that was settled under the old number is
    touched.
    """
    return "\n".join(f"{key}={params[key]}" for key in sorted(params))


def version_hash(sources: Mapping[str, str], params: Mapping[str, Any]) -> str:
    """The identity of a version: its sources and its numbers together."""
    digest = hashlib.sha256()
    digest.update(manifest_hash(manifest(sources)).encode("utf-8"))
    digest.update(b"\n")
    digest.update(params_fingerprint(params).encode("utf-8"))
    return digest.hexdigest()


def decimal_params(params: Mapping[str, Any]) -> dict[str, Decimal]:
    """A stored parameter mapping as :class:`~decimal.Decimal`\\ s."""
    values: dict[str, Decimal] = {}
    for key, value in params.items():
        try:
            values[key] = Decimal(str(value))
        except InvalidOperation:
            continue
    return values


def declared_valid_from(ruleset: Ruleset) -> datetime:
    """When a version's rules apply from, in **valid** time: its own date.

    A ruleset names the date its rules were in force from
    (``valid_from = "2026-03-01"``). A future date is how a section stages a
    change it has already agreed; a *past* date is how it records one it
    agreed before it got round to telling Kompass — the section resolved new
    rates in March, the import happens in May, and the rules were valid from
    March either way. Unset, and the answer is "from now", which is every
    ordinary import.

    A past date used to be refused, on the grounds that honouring it would
    rewrite settled statements. It does not, and that is the point: a
    statement is bound to the closure it copied **when it was created**
    (:func:`~finance.engine.statements.bind`), so what it settles under is
    decided once and no later row can move it. What the refusal actually did
    was make the only correction a section needs unrepresentable, and leave
    valid time pinned to transaction time — so the record could not say that
    Kompass applied one version while a different one had been in force. The
    audit requirement is the opposite of the refusal: both times recorded, so
    that what the system knew and when it knew it stays reconstructible.

    What a backdated version does **not** do is re-settle the statements that
    were created in the gap. They keep their own snapshot and their own rows,
    and re-settling them is a separate, deliberate act that this code does not
    offer.

    The authority for the date is the ruleset package itself — the
    git-versioned configuration repository that §4.2's trust model puts on a
    par with ``settings.toml``, and which is the *Verfahrensdokumentation* the
    GoBD asks for. A date Kompass cannot read is reported and means "from
    now", because an import that silently backdates to the epoch would be
    worse than one that does not backdate at all.
    """
    declared = getattr(ruleset, "valid_from", "")
    now: datetime = timezone.now()
    if not declared:
        return now
    try:
        parsed = datetime.fromisoformat(str(declared))
    except ValueError:
        logger.warning(
            "the ruleset declares valid_from=%r, which is not a date; the version is "
            "valid from now",
            declared,
        )
        return now
    if timezone.is_naive(parsed):
        aware: datetime = timezone.make_aware(parsed)
        parsed = aware
    return parsed


@dataclass(frozen=True)
class DeclaredFields:
    """The three row fields that come from the ruleset *object* itself."""

    name: str
    context_version: int
    valid_from: datetime


def declared_fields(loaded: Ruleset | None, directory: Path, *, name: str = "") -> DeclaredFields:
    """What ``loaded`` says about itself, read inside the query guard.

    These are attribute lookups rather than calls, which is why they ran
    outside the guard: they read like data. They are not. A section's ruleset
    is its own Python, ``name``, ``context_version`` and ``valid_from`` can
    each be a ``property``, and a property is rule code — so it is guarded
    like the rest of it, and a version whose ``name`` queries is a draft with
    a problem rather than a version that got a cursor for free.

    ``name`` given by the caller wins, and short-circuits the read, exactly as
    the ``name or ...`` it replaced did: an explicit name is the importer's,
    not the ruleset's.

    The fourth such attribute, ``permissions``, is read by
    :func:`check_directory` rather than here: it is not a field of the row,
    and reading it is the same refusal for the same reason (#554).
    """
    if loaded is None:
        return DeclaredFields(
            name=name or directory.name, context_version=0, valid_from=timezone.now()
        )
    with no_queries():
        return DeclaredFields(
            name=name or loaded.name,
            context_version=loaded.context_version,
            valid_from=declared_valid_from(loaded),
        )


def failed_cases(ruleset: Ruleset, directory: Path) -> dict[str, list[str]]:
    """The ruleset's own cases that do not pass, by name."""
    cases = directory / CASES_DIRECTORY
    if not cases.is_dir():
        return {}
    return run_cases(ruleset, cases)


def check_directory(directory: Path) -> tuple[Ruleset | None, list[str]]:
    """Everything that can be checked about a ruleset without storing it.

    The whitelist, then the load, then the declared permissions, then the
    cases. Returns the ruleset where it could be loaded at all, and one
    message per problem — which is what ``manage.py checkruleset`` prints and
    what the import gates on.
    """
    sources = read_sources(directory)
    if not sources:
        return None, [f"{directory} holds no Python files"]
    problems = check_sources(sources)
    if problems:
        return None, problems
    try:
        # The whitelist ran three lines up; `check=False` here only avoids
        # parsing every file twice.
        loaded = load(sources, check=False)
    except (RulesetRejected, RulesetInvalid) as refused:
        return None, [str(refused)]
    except Exception as broken:  # a section's own import-time code
        return None, [f"the ruleset could not be loaded: {broken}"]
    try:
        # `permissions` is the fourth attribute a section can write as a
        # `property` — after the three :func:`declared_fields` reads — and the
        # one nothing read at import time, so a ruleset whose `permissions`
        # queries passed every gate here and met the guard later, on the
        # engine's side, where it is only a problem to record. Read and
        # dropped: the point is the refusal, and the engine reads the names
        # again when it needs them (`statement_context`).
        with no_queries():
            tuple(loaded.permissions)
    except Exception as broken:
        return loaded, [f"the ruleset's permissions could not be read: {broken}"]
    failed = failed_cases(loaded, directory)
    problems = [f"case “{case}”: {'; '.join(messages)}" for case, messages in failed.items()]
    return loaded, problems


def import_from_directory(
    directory: Path, *, name: str = "", revision: str = ""
) -> tuple[RuleSet, list[str]]:
    """Import the ruleset in ``directory``, returning its row and its problems.

    An empty problem list means the row is the active version. A non-empty one
    means the row was stored as a draft, the previous version is untouched, and
    the caller has something to shout about.
    """
    sources = read_sources(directory)
    entries = manifest(sources)
    params = parameters_from_settings()
    digest = version_hash(sources, params)
    stored = RuleSet.objects.filter(hash=digest).first()
    if stored is not None:
        if not stored.problems and stored.state != RuleSet.ACTIVE:
            activate(stored)
        return stored, list(stored.problems)

    loaded, problems = check_directory(directory)
    now = timezone.now()
    try:
        declared = declared_fields(loaded, directory, name=name)
    except Exception as broken:  # a field of the section's that runs code
        # Reported rather than raised, like every other way a ruleset can be
        # bad: the row is stored as a draft, the previous version stays active,
        # and the admin and the hourly task both say so instead of falling over
        # (this function's own step 6).
        loaded, declared = None, declared_fields(None, directory, name=name)
        problems = [*problems, f"the ruleset's own fields could not be read: {broken}"]
    predecessor = RuleSet.objects.active()
    row = RuleSet.objects.create(
        name=declared.name,
        hash=digest,
        manifest=entries,
        sources=sources,
        revision=revision,
        engine_version=engine_version(),
        context_version=declared.context_version,
        params=params,
        state=RuleSet.DRAFT,
        problems=problems,
        valid_from=declared.valid_from,
        cases_passed_at=None if problems or loaded is None else timezone.now(),
        supersedes=predecessor,
    )
    if problems:
        return row, problems
    # Backdated — valid time before transaction time — means the row fills an
    # interval that has already passed rather than taking over from now, so
    # whatever version is in force today stays in force. `now` is the one
    # captured above, because `declared_fields` reads its own clock and a
    # version with no declared date would otherwise be a microsecond "in the
    # past" and take the correction path on every ordinary import.
    activate(row, correction=declared.valid_from < now)
    return row, []


def activate(row: RuleSet, *, correction: bool = False) -> None:
    """Put ``row`` into the timeline, in valid time, from its ``valid_from``.

    Every version whose validity covers that instant is closed there —
    usually exactly one, the predecessor; more than one only on a timeline
    that staged two future versions, where closing all of them is the repair.
    Retiring is a *valid*-time statement with a transaction-time stamp of its
    own (:meth:`~finance.store.RuleSet.retire`), so "those rules ended in
    March" and "Kompass was told in May" are both on the record.

    ``correction`` is the backdated case, and it is the caller's to declare
    because the data cannot tell it from a rollback: a row whose validity
    starts in the past while later versions exist fills the interval up to the
    next version's ``valid_from`` and leaves today's version in force. Without
    that cap, a correction resolved in March and imported in May would quietly
    revert an April version that nobody asked to withdraw — valid time's
    answer to "what applies now" would be the March rules.

    Re-activating a version that is already stored (an unchanged package, or a
    section rolling its configuration repository back) is **not** a
    correction, and it keeps the behaviour it has always had: the row's own
    ``valid_from`` is immutable, so a rollback re-opens that old interval
    rather than starting a new one, and the version it rolls back from is
    closed at a date before its own start. That is a lossy way to say "these
    rules apply again" and it is filed rather than changed here, because the
    honest alternative — a second row with the same sources and a new interval
    — collides with ``hash`` being the row's identity.
    """
    moment = row.valid_from
    others = RuleSet.objects.exclude(pk=row.pk).exclude(state=RuleSet.DRAFT)
    covering = others.filter(valid_from__lte=moment).filter(
        Q(valid_to__isnull=True) | Q(valid_to__gt=moment)
    )
    for predecessor in covering:
        predecessor.retire(when=moment)
    until = None
    if correction:
        successor = (
            others.filter(valid_from__gt=moment).order_by("valid_from", "imported_at").first()
        )
        until = None if successor is None else successor.valid_from
    row.activate(until=until)


def active_version() -> RuleSet | None:
    """The version in force now, or ``None`` when nothing is imported."""
    return RuleSet.objects.active()


def ruleset_from_sources(sources: Mapping[str, str]) -> Ruleset:
    """A ruleset from a stored closure, by hash, without touching the disk.

    Checked like any other load: a stored row is not more trustworthy than a
    file, and a row that reached the database before a ban existed — or past
    the model's immutability through an ``update()`` — must not be executed on
    the strength of having been stored once.
    """
    return load(sources)
