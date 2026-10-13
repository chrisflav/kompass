"""The query guard: no database access while rules are being evaluated.

Two prohibitions make an old statement verifiable: a rule may not read the
clock, and a rule may not read the database. The clock is handled by leaving it
out of the context; the database cannot be, because a ruleset is ordinary
Python in the same process as the ORM. So it is enforced instead — every call
into a ruleset runs inside :func:`no_queries`, and a query raises.

**Where the enforcement sits, and why it moved.** The first version wrapped
``connection.execute_wrapper``, which sees only what a Django ``CursorWrapper``
executes. Everything that hands out a cursor another way went past it:
``connection.create_cursor()``, ``connection.chunked_cursor()``,
``connection.connection.cursor()`` on the driver's own connection object, and
``callproc`` on a cursor obtained from any of them. The guard is therefore
installed one level down, on the connection class itself: while a rule is
running, *every* route that opens a connection or hands out a cursor refuses,
and the driver connection is swapped for an object that refuses too. The
execute wrapper stays as a second net, for a cursor that somehow predates the
block.

The patch on the connection class is permanent and inert: it checks a
thread-local depth, so blocking a rule in one worker thread never blocks the
request being served in another. ``django.db.connections`` is itself
thread-local, which is what makes swapping the driver connection safe.

**What this is and is not.** It is enforcement, not a sandbox. A rule that has
got hold of a live cursor object before the block, or that opens its own
connection through the driver module with credentials it read out of the
settings, is past it — and the trust boundary in :mod:`finance.engine.imports`
(whoever writes the rules already holds the database password) is why that is
acceptable. What this does guarantee is that no *ordinary* route to the
database works while rules run, however the rule got to it: the accident this
exists to catch — a rule whose answer changes the next time somebody edits a
member — cannot happen quietly.
"""

import functools
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextlib import ExitStack
from typing import Any
from typing import NoReturn

from django.db import connections

from .errors import QueryDuringEvaluation

#: Everything on a connection that reaches the database or hands out something
#: that can. ``cursor``/``_cursor``/``chunked_cursor`` are Django's API,
#: ``create_cursor`` is the backend's own factory (the one the first version of
#: this guard missed), and ``connect``/``ensure_connection`` are how a
#: connection comes into being at all.
GUARDED_METHODS = (
    "cursor",
    "_cursor",
    "create_cursor",
    "chunked_cursor",
    "ensure_connection",
    "connect",
)

_state = threading.local()
_patched: set[type] = set()
_patch_lock = threading.Lock()


def blocked() -> bool:
    """Whether this thread is currently inside :func:`no_queries`."""
    return getattr(_state, "depth", 0) > 0


def _refuse(what: str) -> NoReturn:
    raise QueryDuringEvaluation(
        "rules must not query the database; everything a rule may read is in "
        f"the context it was given (refused: {what})"
    )


def _refuse_query(execute: Any, sql: Any, params: Any, many: Any, context: Any) -> Any:
    _refuse(str(sql)[:120])


class _RefusingConnection:
    """What ``connection.connection`` is while a rule runs.

    The driver's connection object is a way to the database that knows nothing
    about Django, so it cannot be wrapped — it is taken away instead, and put
    back when the block ends.
    """

    __slots__ = ("real",)

    def __init__(self, real: Any) -> None:
        self.real = real

    def __getattr__(self, name: str) -> Any:
        _refuse(f"connection.connection.{name}")


def _guarded(name: str, original: Any) -> Any:
    @functools.wraps(original)
    def method(self: Any, *args: Any, **kwargs: Any) -> Any:
        if blocked():
            _refuse(f"connection.{name}()")
        return original(self, *args, **kwargs)

    return method


def _patch(wrapper_class: type) -> None:
    """Install the guard on one backend's connection class, once.

    The concrete class rather than ``BaseDatabaseWrapper``: ``create_cursor``
    is defined by each backend, so patching the base would be shadowed by the
    very method that needs guarding.
    """
    with _patch_lock:
        if wrapper_class in _patched:
            return
        for name in GUARDED_METHODS:
            setattr(wrapper_class, name, _guarded(name, getattr(wrapper_class, name)))
        _patched.add(wrapper_class)


@contextmanager
def no_queries() -> Iterator[None]:
    """Block every route to the database made inside the ``with`` block.

    All configured connections, because a rule that found its way to the ORM
    would not care which alias it used, and this thread only, because another
    thread is serving an ordinary request.
    """
    with ExitStack() as stack:
        live = []
        for connection in connections.all():
            _patch(type(connection))
            stack.enter_context(connection.execute_wrapper(_refuse_query))
            if connection.connection is not None:
                live.append(connection)
        for connection in live:
            connection.connection = _RefusingConnection(connection.connection)
        _state.depth = getattr(_state, "depth", 0) + 1
        try:
            yield
        finally:
            _state.depth -= 1
            for connection in live:
                connection.connection = connection.connection.real
