"""The rules engine: everything around a section's rules, none of the rules.

A statement is resolved in three steps, and the engine owns all three.

1. :func:`~finance.engine.context.build_context` reads the statement out of the
   database into frozen values — the only step that touches the ORM.
2. :func:`~finance.engine.evaluation.evaluate` runs the ruleset against that
   context, inside a query blocker, and turns everything that can go wrong into
   a message rather than a traceback on somebody's screen.
3. The engine appends the one transfer that closes the books, with the amount
   it resolves itself.

What a ruleset is allowed to be is :mod:`finance.engine.imports` (the import
whitelist) and :mod:`finance.engine.loader` (loading a version from its stored
source, by hash). The rules themselves are in :mod:`finance.rulesets`.

Step 1 of the refactor has one ruleset, the reference one, compiled into the
image. :func:`active_ruleset` is the seam where step 2 will resolve the
section's own version from the database instead.
"""

from collections.abc import Mapping
from typing import Any

from finance.rules_api import Ruleset
from finance.rulesets.heidelberg import ruleset as reference_ruleset

from .context import build_context
from .context import parameters
from .context import permission_holders
from .errors import EngineError
from .errors import QueryDuringEvaluation
from .errors import RulesetInvalid
from .errors import RulesetRejected
from .evaluation import evaluate
from .evaluation import Result
from .evaluation import sum_amounts
from .guard import no_queries
from .loader import load
from .loader import manifest
from .loader import manifest_hash
from .loader import read_sources
from .loader import source_hash

__all__ = [
    "EngineError",
    "QueryDuringEvaluation",
    "Result",
    "RulesetInvalid",
    "RulesetRejected",
    "active_ruleset",
    "build_context",
    "evaluate",
    "evaluate_statement",
    "load",
    "manifest",
    "manifest_hash",
    "no_queries",
    "parameters",
    "permission_holders",
    "read_sources",
    "source_hash",
    "sum_amounts",
]


def active_ruleset() -> Ruleset:
    """The ruleset a statement is evaluated against.

    Today: the reference ruleset that ships with Kompass. Step 2 of the
    refactor replaces this with the version a statement is bound to, loaded
    from its own snapshot, so that an old statement keeps the rules it was
    created under.
    """
    return reference_ruleset


def evaluate_statement(
    statement: Any,
    *,
    ruleset: Ruleset | None = None,
    inputs: Mapping[str, object] | None = None,
) -> Result:
    """Resolve ``statement`` into transfers.

    The one call the rest of the finance app makes. ``ruleset`` and ``inputs``
    are for a dry run — "what would this statement look like under that
    version, with those answers" — which is what the admin's test pages and the
    parity suite use.
    """
    rules = active_ruleset() if ruleset is None else ruleset
    context = build_context(statement, permissions=rules.permissions, inputs=inputs)
    return evaluate(rules, context)
