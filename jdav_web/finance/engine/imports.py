"""The import whitelist: what a ruleset's source is allowed to mention.

A section's rules are trusted code — whoever can write the configuration
directory already holds the database credentials and the secret key, so
executing Python from it grants no privilege its author does not have. What
this check defends against is not malice but *accident*: a rule that imports
half of Kompass, reads the clock, or opens a file is a rule whose answer can
change behind an old statement's back, and that is the bug this catches, at
import time, with a file and a line.

A ruleset may import:

* itself — relative imports inside its own package,
* :mod:`kompass.rules`, the API of :mod:`finance.rules_api`,
* ``from __future__ import …``, which is a compiler directive,
* and a short list of stdlib modules that reimbursement arithmetic needs:
  ``decimal``, ``math``, ``dataclasses``, ``typing``, ``enum``, ``fractions``,
  ``itertools``, ``functools``, ``collections``.

Everything else is refused, and so is any mention of the usual ways around a
restriction like this one — ``__import__``, ``importlib``, ``exec``, ``eval``,
``open``, ``os``, ``sys``, ``subprocess``, ``socket``, ``random``, ``time``,
``requests``, anything under ``django``, ``getattr``, ``setattr`` — plus a
*call* to ``now``, ``today``, ``utcnow`` or ``fromtimestamp``, which is the
clock, and the **dunder attributes** that walk out of a module and into the
interpreter.

**Where the limit really is.** An earlier version of this docstring, following
§4.2 of the proposal, said the way out was ``getattr(__builtins__, …)`` and
that a rule "cannot reach the ORM even if it imports it". Both were wrong. A
module executed by :mod:`finance.engine.loader` is handed ``__loader__`` and
``__spec__`` like any other module, and
``__loader__.__class__.__init__.__globals__["sys"].modules["django.db"]``
reaches a database connection in one line, through no import at all. Two
things answer that now: the dunder bans below, which refuse that chain where
it is written, and the restricted ``__builtins__`` the loader hands a ruleset,
which holds no ``open``, ``eval``, ``exec`` or ``getattr``.

What remains true: this is a textual check plus a restricted namespace, not a
sandbox. Somebody determined, writing code nobody reviews, in a directory they
can already write ``settings.toml`` into, can still get out — and the trust
boundary of §4.2 is why that is acceptable, not this check. The section's own
CI runs the same bans as ``ruff`` rules, which is where a violation should be
caught first.
"""

import ast
from collections.abc import Mapping

#: Stdlib modules a ruleset may import.
ALLOWED_MODULES = frozenset(
    {
        "decimal",
        "math",
        "dataclasses",
        "typing",
        "enum",
        "fractions",
        "itertools",
        "functools",
        "collections",
    }
)

#: The one Kompass module a ruleset may import.
API_MODULE = "kompass.rules"

#: Names that must not appear at all, however they are reached.
FORBIDDEN_NAMES = frozenset(
    {
        "__import__",
        "importlib",
        "exec",
        "eval",
        "compile",
        "open",
        "os",
        "sys",
        "subprocess",
        "socket",
        "random",
        "time",
        "requests",
        "django",
        "globals",
        "locals",
        "vars",
        "getattr",
        "setattr",
        "delattr",
        "dir",
    }
)

#: Attribute names that walk out of a module and into the interpreter. The
#: chain that made this list necessary was
#: ``__loader__.__class__.__init__.__globals__``, which lands in the engine's
#: own globals and from there in ``sys.modules``.
FORBIDDEN_DUNDERS = frozenset(
    {
        "__class__",
        "__bases__",
        "__base__",
        "__mro__",
        "__subclasses__",
        "__globals__",
        "__builtins__",
        "__loader__",
        "__spec__",
        "__dict__",
        "__code__",
        "__func__",
        "__self__",
        "__init__",
        "__new__",
        "__getattribute__",
        "__reduce__",
        "__reduce_ex__",
    }
)

#: Attribute names that read the clock. Refused when they are *called*, so
#: that a field or a key that happens to be named ``now`` is not an offence.
CLOCK_CALLS = frozenset({"now", "today", "utcnow", "fromtimestamp"})


def _root(module: str) -> str:
    return module.partition(".")[0]


def _allowed_module(module: str) -> bool:
    return module == API_MODULE or _root(module) in ALLOWED_MODULES


def check_source(path: str, source: str) -> list[str]:
    """Every problem with one file, as ``"path:line: message"``.

    A syntax error is one problem, named like the rest, so that a broken
    ruleset is refused rather than raising out of the importer.
    """
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as error:
        return [f"{path}:{error.lineno or 0}: cannot be parsed: {error.msg}"]

    problems: list[str] = []

    def refuse(node: ast.AST, message: str) -> None:
        problems.append(f"{path}:{getattr(node, 'lineno', 0)}: {message}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _allowed_module(alias.name):
                    refuse(node, f"may not import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue  # a relative import inside the ruleset's own package
            module = node.module or ""
            if module == "__future__":
                continue  # a compiler directive, not an import of anything
            if not _allowed_module(module):
                refuse(node, f"may not import from {module}")
        elif isinstance(node, ast.Name):
            # A bare name as well as an attribute: `__builtins__["open"]`
            # never touches an attribute, and `__loader__` is a module global.
            if node.id in FORBIDDEN_NAMES or node.id in FORBIDDEN_DUNDERS:
                refuse(node, f"may not use {node.id}")
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_DUNDERS:
                refuse(node, f"may not reach through {node.attr}")
            elif node.attr in FORBIDDEN_NAMES:
                refuse(node, f"may not use {node.attr}")
        elif isinstance(node, ast.Call):
            called = node.func
            if isinstance(called, ast.Attribute) and called.attr in CLOCK_CALLS:
                refuse(node, f"may not read the clock ({called.attr}())")
    return problems


def check_sources(sources: Mapping[str, str]) -> list[str]:
    """Every problem with a whole ruleset, file by file in path order."""
    problems: list[str] = []
    for path in sorted(sources):
        problems.extend(check_source(path, sources[path]))
    return problems
