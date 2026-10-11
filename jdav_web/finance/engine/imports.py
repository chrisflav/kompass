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
* and a short list of stdlib modules that reimbursement arithmetic needs:
  ``decimal``, ``math``, ``dataclasses``, ``typing``, ``enum``, ``fractions``,
  ``itertools``, ``functools``, ``collections``.

Everything else is refused, and so is any mention of the usual ways around a
restriction like this one — ``__import__``, ``importlib``, ``exec``, ``eval``,
``open``, ``os``, ``sys``, ``subprocess``, ``socket``, ``random``, ``time``,
``requests``, anything under ``django`` — plus ``datetime.now`` and
``date.today``, which are the clock.

**What this is not.** It is a textual check on the source about to be
executed, so a determined author can defeat it (``getattr(__builtins__,
...)``); it is not a sandbox and nothing here claims otherwise. The section's
own CI runs the same bans as ``ruff`` rules, which is where a violation should
be caught first.
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
    }
)

#: Attribute names that read the clock.
FORBIDDEN_ATTRIBUTES = frozenset({"now", "today", "utcnow", "fromtimestamp"})


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
            if not _allowed_module(module):
                refuse(node, f"may not import from {module}")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES:
                refuse(node, f"may not use {node.id}")
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRIBUTES:
                refuse(node, f"may not read the clock ({node.attr})")
            elif node.attr in FORBIDDEN_NAMES:
                refuse(node, f"may not use {node.attr}")
    return problems


def check_sources(sources: Mapping[str, str]) -> list[str]:
    """Every problem with a whole ruleset, file by file in path order."""
    problems: list[str] = []
    for path in sorted(sources):
        problems.extend(check_source(path, sources[path]))
    return problems
