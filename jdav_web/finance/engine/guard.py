"""The query guard: no database access while rules are being evaluated.

Two prohibitions make an old statement verifiable: a rule may not read the
clock, and a rule may not read the database. The clock is handled by leaving it
out of the context; the database cannot be, because a ruleset is ordinary
Python in the same process as the ORM. So it is enforced instead — every call
into a ruleset runs inside :func:`no_queries`, and a query raises.

This is a guard against *accident*, not a sandbox: a rule that reaches for a
model is a rule whose answer would change the next time somebody edits a
member, and that is the bug worth catching.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextlib import ExitStack
from typing import Any

from django.db import connections

from .errors import QueryDuringEvaluation


def _refuse(execute: Any, sql: Any, params: Any, many: Any, context: Any) -> Any:
    raise QueryDuringEvaluation(
        "rules must not query the database; everything a rule may read is in "
        f"the context it was given (refused: {str(sql)[:120]})"
    )


@contextmanager
def no_queries() -> Iterator[None]:
    """Block every database query made inside the ``with`` block.

    Wraps all configured connections, because a rule that found its way to the
    ORM would not care which alias it used.
    """
    with ExitStack() as stack:
        for connection in connections.all():
            stack.enter_context(connection.execute_wrapper(_refuse))
        yield
