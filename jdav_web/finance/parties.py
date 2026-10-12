"""How a transfer's two ends are written down.

Three strings, in a module of their own because both sides need them: the store
uses them as a column's choices, and the engine maps a
:class:`kompass.rules.Party` onto them. Keeping them here rather than in either
one is what lets the engine stay typed — the models module is deliberately
outside ``mypy``'s scope, so a constant read from it is ``Any`` — and it costs
one leaf module that imports nothing.
"""

from typing import Final

#: A person, identified by their member row.
MEMBER: Final = "member"
#: The section's own money.
SECTION: Final = "section"
#: The participants' contributions, as one party.
PARTICIPANTS: Final = "participants"
