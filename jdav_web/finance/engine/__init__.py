"""The rules engine: everything around a section's rules, none of the rules.

A statement is resolved in three steps, and the engine owns all three.

1. :func:`~finance.engine.context.build_context` reads the statement out of the
   database into frozen values — the only step that touches the ORM.
2. :func:`~finance.engine.evaluation.evaluate` runs the ruleset against that
   context, inside a query blocker, and turns everything that can go wrong into
   a message rather than a traceback on somebody's screen.
3. The engine appends the one transfer that closes the books, with the amount
   it resolves itself.

Around those: :mod:`finance.engine.imports` (what a ruleset may import),
:mod:`finance.engine.loader` (loading a version from its stored source, by
hash), :mod:`finance.engine.versions` (importing and activating a version) and
:mod:`finance.engine.statements` (binding a statement to a version, and writing
its transfers down as rows). The rules themselves are in
:mod:`finance.rulesets`.

Adding a test around the query guard, the loader or the approval gate: read
:mod:`finance.tests.harness` first. Three tests here once passed while testing
nothing of the production path, and an audit of the rest found four more fixes
that no test would have missed; that module is the recipe for not writing the
next one, and the two helpers that make it cheap.
"""

from .answers import coerce_input
from .answers import typed_inputs
from .approval import ConstraintState
from .approval import fully_approved
from .approval import may_sign
from .approval import resolve_eligibility
from .approval import states as approval_states
from .context import build_context
from .context import parameters
from .context import permission_holders
from .context import statement_inputs
from .declared import ask
from .declared import options_from
from .declared import supplied
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
from .statements import active_ruleset
from .statements import bind
from .statements import cents_of
from .statements import current_constraint_rows
from .statements import evaluate_statement
from .statements import freeze
from .statements import live_rows
from .statements import materialise
from .statements import result_from_rows
from .statements import rows_exist
from .statements import ruleset_for
from .statements import statement_context
from .statements import statement_params
from .statements import verify
from .versions import active_version
from .versions import check_directory
from .versions import configured_directory
from .versions import decimal_params
from .versions import engine_version
from .versions import import_from_directory
from .versions import reference_directory
from .versions import ruleset_directory
from .versions import ruleset_from_sources

__all__ = [
    "ConstraintState",
    "EngineError",
    "QueryDuringEvaluation",
    "Result",
    "RulesetInvalid",
    "RulesetRejected",
    "active_ruleset",
    "active_version",
    "approval_states",
    "ask",
    "bind",
    "build_context",
    "cents_of",
    "check_directory",
    "coerce_input",
    "configured_directory",
    "current_constraint_rows",
    "decimal_params",
    "engine_version",
    "evaluate",
    "evaluate_statement",
    "freeze",
    "fully_approved",
    "import_from_directory",
    "live_rows",
    "load",
    "manifest",
    "manifest_hash",
    "materialise",
    "may_sign",
    "no_queries",
    "options_from",
    "parameters",
    "permission_holders",
    "read_sources",
    "reference_directory",
    "resolve_eligibility",
    "result_from_rows",
    "rows_exist",
    "ruleset_directory",
    "ruleset_for",
    "ruleset_from_sources",
    "source_hash",
    "statement_context",
    "statement_inputs",
    "statement_params",
    "supplied",
    "sum_amounts",
    "typed_inputs",
    "verify",
]
