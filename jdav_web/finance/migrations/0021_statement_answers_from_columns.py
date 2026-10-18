"""The four Heidelberg columns become four answers in ``inputs``.

What moves, and from where. ``night_cost``, ``allowance_to``, ``subsidy_to``
and ``ljp_to`` are read **from the columns**, never from ``inputs``, and that is
the whole point of this migration rather than an implementation detail:
``Statement.inputs`` has been written beside those columns and read by nothing
since ``0018``, so it drifts. An admin edit writes a column and leaves the
field stale; a key the rules stopped asking for stays in it, because the API
merged rather than replaced. Reading it here would let a stale answer win over
the one a person actually saved. ``finance/inputs.py`` says so in a warning
addressed to this file.

What it does to live data, statement by statement:

* ``night_cost`` becomes the text of the decimal — ``"27.00"``, never a binary
  float, which is how every amount is written in JSON in this app.
* ``allowance_to`` becomes the member ids, sorted, which is the order
  ``statement_inputs`` fed the rules before this and so cannot change an
  amount.
* ``subsidy_to`` and ``ljp_to`` become the member id or ``null``.
* Any other key already in ``inputs`` is kept. Only these four are overwritten,
  because only these four have a column to be authoritative.

**Reversibility.** Both directions are implemented and tested. Forwards is
additive: the columns are not touched, so this migration alone can be reversed
by writing the answers back into them, and ``0022`` is what actually drops
them. Reversing ``0022`` *without* reversing this one leaves the columns empty.

Four things reversing cannot do. The first two match what the dropped columns
would have done anyway:

* a member deleted between the two runs comes back as ``null``, because the
  columns were ``SET_NULL`` and the through rows cascaded;
* the order of ``allowance_to`` is lost to a set that never had one;
* an amount over ``999.99`` does not fit the ``max_digits=5`` column it would
  be written back into, so reversing a statement whose price per night was
  raised *after* this ran fails rather than truncating it. The edge bounds a
  money answer at ``max_digits=7`` (:data:`finance.inputs.MONEY_MAX`), because
  a section may reimburse more than that column ever held;
* and the stale value ``inputs`` held for one of these four keys is overwritten
  forwards and not put back. Benign — nothing read that field — and said out
  loud because "reversible" should mean what it says.
"""

from decimal import Decimal

from django.db import migrations

#: The resolution every amount in this app is written at.
CENTS = Decimal("0.01")

#: The keys this migration owns, and so the ones it overwrites.
COLUMN_KEYS = ("night_cost", "allowance_to", "subsidy_to", "ljp_to")


def answers_from_columns(apps, schema_editor):
    Statement = apps.get_model("finance", "Statement")
    alias = schema_editor.connection.alias
    rows = Statement.objects.using(alias).prefetch_related("allowance_to")
    for statement in rows:
        answers = {
            key: value for key, value in (statement.inputs or {}).items() if key not in COLUMN_KEYS
        }
        # Quantised to cents, so the text does not depend on what the backend
        # hands back for a column that was never written: SQLite answers
        # ``Decimal("0")`` where MariaDB answers ``Decimal("0.00")``.
        answers["night_cost"] = str(Decimal(statement.night_cost or 0).quantize(CENTS))
        answers["allowance_to"] = sorted(member.pk for member in statement.allowance_to.all())
        answers["subsidy_to"] = statement.subsidy_to_id
        answers["ljp_to"] = statement.ljp_to_id
        statement.inputs = answers
        statement.save(using=alias, update_fields=["inputs"])


def columns_from_answers(apps, schema_editor):
    Statement = apps.get_model("finance", "Statement")
    Member = apps.get_model("members", "Member")
    alias = schema_editor.connection.alias
    for statement in Statement.objects.using(alias):
        answers = statement.inputs or {}
        statement.night_cost = Decimal(str(answers.get("night_cost") or 0))
        # A member who no longer exists cannot go back into a foreign key, and
        # would not have been in one: both columns were `SET_NULL`.
        wanted = [int(pk) for pk in (answers.get("allowance_to") or [])]
        wanted += [
            int(answers[key]) for key in ("subsidy_to", "ljp_to") if answers.get(key) is not None
        ]
        alive = set(Member.objects.using(alias).filter(pk__in=wanted).values_list("pk", flat=True))
        statement.subsidy_to_id = _alive(answers.get("subsidy_to"), alive)
        statement.ljp_to_id = _alive(answers.get("ljp_to"), alive)
        statement.save(using=alias, update_fields=["night_cost", "subsidy_to", "ljp_to"])
        statement.allowance_to.set(
            pk
            for pk in (int(value) for value in (answers.get("allowance_to") or []))
            if pk in alive
        )


def _alive(value, alive):
    """``value`` as a member id, or ``None`` when nobody by that id is left."""
    if value is None:
        return None
    return int(value) if int(value) in alive else None


class Migration(migrations.Migration):
    dependencies = [("finance", "0020_approval_signers")]

    operations = [migrations.RunPython(answers_from_columns, columns_from_answers)]
