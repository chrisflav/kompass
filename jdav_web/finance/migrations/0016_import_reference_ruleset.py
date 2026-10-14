"""Import the reference ruleset, bind it to what exists, write down the books.

Four things happen here, and the order matters.

1. **The reference ruleset becomes the first stored version.** Its sources are
   read from the package that ships in the image, hashed exactly the way
   ``finance.engine.loader`` hashes them, and stored with the section's current
   numbers as its parameters. From here on ``[finance] ruleset`` in
   ``settings.toml`` is what a section points at instead.
2. **Every statement is bound to it**, which is what a statement created from
   now on does by itself.
3. **A submitted or paid statement keeps the numbers it was submitted with.**
   Its ``settings_snapshot`` — the floats the old code captured at ``submit()``
   — becomes the parameters of its own snapshot, so no settled figure moves by
   a cent. This is the trick ``0013_statement_settings_snapshot`` used, in the
   other direction.
4. **A paid statement's transactions become its obligations.** For a confirmed
   statement the transactions *are* what happened, so they are the honest
   record to materialise, and they are frozen on arrival.

Statements that are submitted but not yet paid out are deliberately left
without rows: they are still being worked on, their figures are still the
rules' to compute, and a row written here would freeze a half-finished payout.
They materialise on their next touch, which is what the engine does anyway.

The algorithm in :func:`_hash` is a copy of ``finance.engine.versions`` rather
than an import of it: a migration has to keep meaning the same thing in five
years, and importing today's engine into it would make that a matter of luck.
``finance.tests.store`` asserts the two agree.
"""

import hashlib
from pathlib import Path

from django.conf import settings
from django.db import migrations
from django.utils import timezone

#: The settings a version's parameters are taken from. Copied, for the reason
#: in the module docstring.
PARAMETER_KEYS = (
    "ALLOWANCE_PER_DAY",
    "MAX_NIGHT_COST",
    "AID_PER_KM_TRAIN",
    "AID_PER_KM_CAR",
    "EXCURSION_ORG_FEE",
    "LJP_CONTRIBUTION_PER_DAY",
    "LJP_TAX",
)

REFERENCE = Path(__file__).resolve().parent.parent / "rulesets" / "heidelberg"


def _sources(directory):
    return {
        path.relative_to(directory).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(directory.rglob("*.py"))
    }


def _manifest(sources):
    return {
        path: hashlib.sha256(sources[path].encode("utf-8")).hexdigest() for path in sorted(sources)
    }


def _manifest_hash(manifest):
    text = "".join(f"{path}:{manifest[path]}\n" for path in sorted(manifest))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hash(manifest, params):
    """A version's identity: its sources and its numbers together."""
    digest = hashlib.sha256()
    digest.update(_manifest_hash(manifest).encode("utf-8"))
    digest.update(b"\n")
    digest.update("\n".join(f"{key}={params[key]}" for key in sorted(params)).encode("utf-8"))
    return digest.hexdigest()


def _parameters(settings):
    return {key: str(getattr(settings, key, 0)) for key in PARAMETER_KEYS}


def _snapshot_params(statement, fallback):
    """The numbers a statement keeps: its own, where it captured any."""
    captured = statement.settings_snapshot or {}
    params = dict(fallback)
    for key in PARAMETER_KEYS:
        if key in captured:
            params[key] = str(captured[key])
    return params


def import_reference(apps, _schema_editor):
    RuleSet = apps.get_model("finance", "RuleSet")
    Statement = apps.get_model("finance", "Statement")
    Obligation = apps.get_model("finance", "Obligation")

    sources = _sources(REFERENCE)
    manifest = _manifest(sources)
    now = timezone.now()
    params = _parameters(settings)
    digest = _hash(manifest, params)
    version, _created = RuleSet.objects.get_or_create(
        hash=digest,
        defaults={
            "name": "heidelberg",
            "manifest": manifest,
            "sources": sources,
            "revision": "",
            "engine_version": "",
            "context_version": 1,
            "params": params,
            "state": 1,  # RuleSet.ACTIVE
            "problems": [],
            "valid_from": now,
            "activated_at": now,
            "cases_passed_at": None,
        },
    )

    for statement in Statement.objects.all().iterator():
        statement.ruleset_id = version.pk
        statement.ruleset_hash = digest
        statement.ruleset_snapshot = {
            "hash": digest,
            "name": version.name,
            "sources": sources,
            "params": _snapshot_params(statement, params),
            "engine_version": "",
            "context_version": 1,
            "revision": "",
        }
        statement.save(update_fields=["ruleset", "ruleset_hash", "ruleset_snapshot"])

        if statement.status != 2:  # not paid out: see the module docstring
            continue
        rows = []
        position = 0
        net = 0
        for transaction in statement.transaction_set.order_by("pk"):
            cents = int((transaction.amount * 100).to_integral_value())
            member_id = transaction.member_id
            name = f"{transaction.member.prename} {transaction.member.lastname}".strip()
            owed_to_member = cents >= 0
            rows.append(
                Obligation(
                    statement_id=statement.pk,
                    position=position,
                    source_kind="section" if owed_to_member else "member",
                    source_member_id=None if owed_to_member else member_id,
                    source_name="" if owed_to_member else name,
                    destination_kind="member" if owed_to_member else "section",
                    destination_member_id=member_id if owed_to_member else None,
                    destination_name=name if owed_to_member else "",
                    amount_cents=abs(cents),
                    category="legacy",
                    label=transaction.reference[:200],
                    explanation="",
                    rule_id="legacy",
                    rule_version=digest,
                    frozen_at=statement.confirmed_date or now,
                )
            )
            position += 1
            net += cents
        if not rows:
            continue
        # The balancing row the engine would have added: what the participants
        # contributed is what the section paid out net.
        rows.append(
            Obligation(
                statement_id=statement.pk,
                position=position,
                source_kind="participants" if net >= 0 else "section",
                destination_kind="section" if net >= 0 else "participants",
                amount_cents=abs(net),
                category="participant_contribution",
                label="",
                explanation="",
                rule_id="balance",
                rule_version=digest,
                frozen_at=statement.confirmed_date or now,
            )
        )
        Obligation.objects.bulk_create(rows)


def unbind(apps, _schema_editor):
    """Undo the data, so the schema migration can be reversed."""
    Obligation = apps.get_model("finance", "Obligation")
    Statement = apps.get_model("finance", "Statement")
    RuleSet = apps.get_model("finance", "RuleSet")
    Obligation.objects.all().delete()
    Statement.objects.all().update(ruleset=None, ruleset_hash="", ruleset_snapshot={})
    RuleSet.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("finance", "0015_ruleset_store")]

    operations = [migrations.RunPython(import_reference, unbind)]
