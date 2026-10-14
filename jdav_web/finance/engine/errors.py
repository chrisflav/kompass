"""The engine's own exceptions.

A problem with a *statement* is never an exception — it is a message in the
error list a ruleset returns (see :meth:`kompass.rules.Ruleset.transfers`).
These are the problems with a *ruleset*: it queried the database, it imports
something it may not, it cannot be loaded at all.
"""


class EngineError(Exception):
    """Base class for everything the engine itself refuses to do."""


class QueryDuringEvaluation(EngineError):
    """A ruleset tried to reach the database while it was being evaluated.

    Evaluation is pure by construction: the engine wraps it in a query blocker,
    so a rule that reads a row — directly, or by touching a lazy relation that
    slipped into the context — fails here instead of quietly making an old
    statement depend on today's data.
    """


class RulesetRejected(EngineError):
    """A ruleset's source was refused before it was executed.

    Carries one message per problem found, each naming a file and a line.
    """

    def __init__(self, problems: list[str]) -> None:
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


class RulesetInvalid(EngineError):
    """A ruleset's source loaded, but what it exports is not usable.

    No ``ruleset`` attribute, something that is not a
    :class:`kompass.rules.Ruleset`, or one written against a newer context
    version than this Kompass offers.
    """
