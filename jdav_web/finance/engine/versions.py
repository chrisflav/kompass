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
import os
import platform
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from decimal import InvalidOperation
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone
from finance.rules_api import Ruleset
from finance.store import RuleSet

from .cases import run_cases
from .context import PARAMETER_KEYS
from .errors import RulesetInvalid
from .errors import RulesetRejected
from .imports import check_sources
from .loader import load
from .loader import manifest
from .loader import manifest_hash
from .loader import read_sources

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
    """When a version's rules apply from: its own date, or now.

    A ruleset may name a future date (``valid_from = "2027-01-01"``), which is
    how a section stages a change it has already agreed. A date in the past is
    not honoured — that would rewrite settled statements — so anything but a
    future date means "from now".
    """
    declared = getattr(ruleset, "valid_from", "")
    now: datetime = timezone.now()
    if not declared:
        return now
    try:
        parsed = datetime.fromisoformat(str(declared))
    except ValueError:
        return now
    if timezone.is_naive(parsed):
        aware: datetime = timezone.make_aware(parsed)
        parsed = aware
    return parsed if parsed > now else now


def failed_cases(ruleset: Ruleset, directory: Path) -> dict[str, list[str]]:
    """The ruleset's own cases that do not pass, by name."""
    cases = directory / CASES_DIRECTORY
    if not cases.is_dir():
        return {}
    return run_cases(ruleset, cases)


def check_directory(directory: Path) -> tuple[Ruleset | None, list[str]]:
    """Everything that can be checked about a ruleset without storing it.

    The whitelist, then the load, then the cases. Returns the ruleset where it
    could be loaded at all, and one message per problem — which is what
    ``manage.py checkruleset`` prints and what the import gates on.
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
    predecessor = RuleSet.objects.active()
    row = RuleSet.objects.create(
        name=name or (loaded.name if loaded is not None else directory.name),
        hash=digest,
        manifest=entries,
        sources=sources,
        revision=revision,
        engine_version=engine_version(),
        context_version=loaded.context_version if loaded is not None else 0,
        params=params,
        state=RuleSet.DRAFT,
        problems=problems,
        valid_from=declared_valid_from(loaded) if loaded is not None else timezone.now(),
        cases_passed_at=None if problems or loaded is None else timezone.now(),
        supersedes=predecessor,
    )
    if problems:
        return row, problems
    activate(row)
    return row, []


def activate(row: RuleSet) -> None:
    """Put ``row`` in force and close the validity of the version it replaces."""
    predecessor = RuleSet.objects.active()
    if predecessor is not None and predecessor.pk != row.pk:
        predecessor.retire(when=row.valid_from)
    row.activate()


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
