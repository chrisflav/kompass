"""Writing a statement's answers in a fixture.

``night_cost``, ``allowance_to``, ``subsidy_to`` and ``ljp_to`` were columns,
so a fixture wrote them the way it writes any field: ``statement.subsidy_to =
fritz``, ``statement.allowance_to.add(m)``. They are keys in
``Statement.inputs`` now, and these two put them there — :func:`answer` sets
answers, :func:`also` adds somebody to a party-valued one.

Neither validates, on purpose. Checking an answer against the declaration it
belongs to is :func:`finance.inputs.clean`'s job at the edge, and a fixture
that went through it could not set up the states several of these tests exist
for: an allowance recipient who does not lead the trip is exactly what
``allowance_to_valid`` and the admin's confirm guard are tested with.
"""


def answer(statement, **values):
    """Record ``values`` as ``statement``'s answers, keeping the rest."""
    statement.inputs = dict(statement.inputs or {}, **values)
    statement.save(update_fields=["inputs"])
    return statement


def also(statement, key, *members):
    """Add ``members`` to the party-valued answer ``key``."""
    current = statement.answer_member_ids(key)
    return answer(statement, **{key: sorted({*current, *(member.pk for member in members)})})


def without(statement, key, *members):
    """Take ``members`` out of the party-valued answer ``key``."""
    gone = {member.pk for member in members}
    kept = [pk for pk in statement.answer_member_ids(key) if pk not in gone]
    return answer(statement, **{key: kept})
