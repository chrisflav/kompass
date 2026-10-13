"""Loading a ruleset from its source, by hash.

A ruleset version has to stay loadable for as long as a statement is bound to
it, which is natural for a string and awkward for a module — unless the module
*is* a string. It is: a version is a mapping ``{relative_path: source}``, and
this module executes that mapping into a package of its own, named after the
hash of its contents (``kompass_rules_<hash12>``), served by a finder on
:data:`sys.meta_path`.

Two consequences are the point of the design. Two versions of a section's
rules coexist in one process, because they are two differently named packages,
so a draft bound to last month's version evaluates against last month's rules
while the next statement uses this month's — no ``sys.path`` juggling, no
``sys.modules`` collision, no process restart. And nothing is ever read from
disk at evaluation time, so what runs is what was hashed.

What the hash proves, and what it does not: it is the exact text that was
loaded, nothing more. It is not invariant under reformatting (a reformat is a
new version) and it says nothing about behaviour. That is acceptable because
nothing *depends* on the hash — a statement depends on its own snapshot — and
it is why the resolved transfers are materialised rather than re-derived (step
2 of the refactor).
"""

import builtins
import hashlib
import sys
import threading
from collections.abc import Mapping
from importlib import import_module
from importlib.abc import Loader
from importlib.abc import MetaPathFinder
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType
from typing import Any

from finance.rules_api import CONTEXT_VERSION
from finance.rules_api import Ruleset

from .errors import RulesetInvalid
from .errors import RulesetRejected
from .imports import check_sources

#: The prefix of every package a stored ruleset is executed into.
PACKAGE_PREFIX = "kompass_rules_"

#: The builtins a ruleset is executed with: a whitelist, not a blacklist.
#:
#: Absent from it, on purpose: ``open``, ``eval``, ``exec``, ``compile``,
#: ``getattr``, ``setattr``, ``globals``, ``vars``, ``dir``, ``input``,
#: ``breakpoint``, ``help``. ``__import__`` and ``__build_class__`` *are*
#: present because the interpreter calls them for an ``import`` statement and a
#: ``class`` statement; what may be imported is constrained by the whitelist in
#: :mod:`finance.engine.imports` rather than by removing the hook.
SAFE_BUILTIN_NAMES = (
    "__build_class__",
    "__import__",
    "__name__",
    "abs",
    "all",
    "any",
    "bool",
    "dict",
    "divmod",
    "enumerate",
    "filter",
    "float",
    "format",
    "frozenset",
    "int",
    "isinstance",
    "issubclass",
    "iter",
    "len",
    "list",
    "map",
    "max",
    "min",
    "next",
    "object",
    "property",
    "range",
    "repr",
    "reversed",
    "round",
    "set",
    "slice",
    "sorted",
    "staticmethod",
    "str",
    "sum",
    "super",
    "tuple",
    "zip",
    # Exceptions a rule may legitimately name.
    "ArithmeticError",
    "AssertionError",
    "AttributeError",
    "Exception",
    "KeyError",
    "LookupError",
    "TypeError",
    "ValueError",
    "ZeroDivisionError",
)

#: The attribute a ruleset package has to export.
EXPORT = "ruleset"


def manifest(sources: Mapping[str, str]) -> dict[str, str]:
    """``{relative_path: sha256}`` over a version's whole source closure."""
    return {
        path: hashlib.sha256(sources[path].encode("utf-8")).hexdigest() for path in sorted(sources)
    }


def manifest_hash(entries: Mapping[str, str]) -> str:
    """The hash *of* a manifest: one line per file, in path order.

    Hashing the manifest rather than the concatenated sources means the digest
    changes when a file is renamed or removed, not only when its contents
    change.
    """
    text = "".join(f"{path}:{entries[path]}\n" for path in sorted(entries))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_hash(sources: Mapping[str, str]) -> str:
    """The version hash of a source closure."""
    return manifest_hash(manifest(sources))


def read_sources(directory: Path) -> dict[str, str]:
    """Every ``*.py`` file under ``directory``, keyed by its relative path.

    Paths are POSIX-style whatever the host, so the same ruleset hashes the
    same everywhere.
    """
    sources: dict[str, str] = {}
    for path in sorted(directory.rglob("*.py")):
        sources[path.relative_to(directory).as_posix()] = path.read_text(encoding="utf-8")
    return sources


def safe_builtins() -> dict[str, Any]:
    """The builtins a ruleset is executed with (see :data:`SAFE_BUILTIN_NAMES`)."""
    available = vars(builtins)
    return {name: available[name] for name in SAFE_BUILTIN_NAMES if name in available}


class _StoredLoader(Loader):
    """Executes one stored file as one module."""

    def __init__(self, package: str, path: str, source: str) -> None:
        self.package = package
        self.path = path
        self.source = source

    def create_module(self, spec: ModuleSpec) -> ModuleType | None:
        return None

    def exec_module(self, module: ModuleType) -> None:
        # The filename is what a traceback shows a rule author, so it names the
        # version and the file inside it rather than a temporary path.
        code = compile(self.source, f"<{self.package}>/{self.path}", "exec")
        # A restricted `__builtins__`, set before the exec so the interpreter
        # does not install the real one. It is the second half of the import
        # whitelist: the textual check refuses the chain
        # `__loader__.__class__.__init__.__globals__` where it is written, and
        # this makes `open`, `eval` and `getattr` absent even where it is not.
        module.__dict__["__builtins__"] = safe_builtins()
        # Executing the section's own code is the job; see the module docstring.
        exec(code, module.__dict__)


class StoredSourcesFinder(MetaPathFinder):
    """Serves the packages of every ruleset version loaded in this process.

    One finder for all versions: it is installed on :data:`sys.meta_path` once
    and each :meth:`register` adds a package name it answers for.
    """

    def __init__(self) -> None:
        self.packages: dict[str, Mapping[str, str]] = {}

    def register(self, package: str, sources: Mapping[str, str]) -> None:
        self.packages[package] = sources

    def _resolve(self, fullname: str) -> tuple[str, str, bool] | None:
        """``(package, path, is_package)`` for a module this finder serves."""
        for package, sources in self.packages.items():
            if fullname == package:
                return package, "__init__.py", True
            prefix = f"{package}."
            if not fullname.startswith(prefix):
                continue
            relative = fullname[len(prefix) :].replace(".", "/")
            if f"{relative}/__init__.py" in sources:
                return package, f"{relative}/__init__.py", True
            if f"{relative}.py" in sources:
                return package, f"{relative}.py", False
        return None

    def find_spec(
        self, fullname: str, path: Any = None, target: ModuleType | None = None
    ) -> ModuleSpec | None:
        resolved = self._resolve(fullname)
        if resolved is None:
            return None
        package, relative, is_package = resolved
        source = self.packages[package][relative]
        spec = ModuleSpec(fullname, _StoredLoader(package, relative, source), is_package=is_package)
        if is_package:
            # Submodules are served from the stored closure, not from a
            # directory, so the search path is deliberately empty.
            spec.submodule_search_locations = []
        return spec


#: The process-wide finder. Installed on first use and never removed: a
#: package it serves may still be referenced by a loaded module.
FINDER = StoredSourcesFinder()

#: Serialises registration and import. uwsgi runs this with four threads per
#: process and recycles on RSS, so a cold worker taking two concurrent
#: requests is routine rather than exotic.
#:
#: One lock for *all* versions, not one per version: loading two different
#: rulesets at once therefore waits, which is deliberate. The thing being
#: protected is the finder's registry — a process-wide mapping — and a load
#: costs milliseconds and happens once per version per process, so a shared
#: lock is the cheap correct choice rather than a bottleneck. It is an
#: ``RLock`` because a ruleset's own module body may import a submodule of
#: itself, which re-enters this.
_LOAD_LOCK = threading.RLock()


def _install() -> None:
    if FINDER not in sys.meta_path:
        sys.meta_path.append(FINDER)


def package_name(sources: Mapping[str, str]) -> str:
    """The package name a source closure is executed into."""
    return f"{PACKAGE_PREFIX}{source_hash(sources)[:12]}"


def load(sources: Mapping[str, str], *, check: bool = True) -> Ruleset:
    """The ruleset a source closure exports.

    Refuses sources the import whitelist rejects (:class:`RulesetRejected`),
    sources that do not export a usable ``ruleset`` and rulesets written
    against a newer context than this Kompass offers
    (:class:`RulesetInvalid`).

    The whitelist runs on **every** load, stored rows included. It used to be
    an import-time check only, which meant a row that reached the database
    before a ban existed — or through an `update()` — was executed unchecked,
    and the admin's dry run would happily run it. ``check=False`` exists for
    the engine's own tests, which construct sources this check would refuse on
    purpose.
    """
    if "__init__.py" not in sources:
        raise RulesetInvalid("a ruleset package needs an __init__.py")
    if check:
        problems = check_sources(sources)
        if problems:
            raise RulesetRejected(problems)
    package = package_name(sources)
    with _LOAD_LOCK:
        FINDER.register(package, sources)
        _install()
        # `import_module`, not a hand-rolled `module_from_spec` plus
        # `sys.modules[...] = module` plus `exec_module`: that sequence
        # publishes a half-initialised module and bypasses importlib's
        # per-module lock, so a second thread arriving mid-exec reads a module
        # with no `ruleset` in it yet, `as_ruleset` refuses it, and the caller
        # falls back to a *different* section's rules — and materialises them.
        # The lock around the registration is this module's own: two threads
        # loading two versions at once must not race on the finder's registry.
        #
        # One residue is left on purpose: if a module body raises halfway, the
        # submodules it had already imported stay in `sys.modules`. Clearing
        # them would mean deciding which of them a *concurrent* load of the
        # same version is relying on, and the next load of this closure
        # re-executes the package itself (importlib removed the failed module,
        # not its dependencies) and reuses them, which is correct because they
        # are the same immutable sources. The cost is a little memory in a
        # process that has seen a broken ruleset.
        module = import_module(package)
    return as_ruleset(module)


def as_ruleset(module: ModuleType) -> Ruleset:
    """The ``ruleset`` a loaded module exports, checked.

    Also used for the reference ruleset, which is an ordinary package in this
    repository rather than a stored closure.
    """
    exported = getattr(module, EXPORT, None)
    if not isinstance(exported, Ruleset):
        raise RulesetInvalid(f"{module.__name__} does not export a Ruleset as `{EXPORT}`")
    if exported.context_version > CONTEXT_VERSION:
        raise RulesetInvalid(
            f"{module.__name__} is written against context version "
            f"{exported.context_version}, this Kompass offers {CONTEXT_VERSION}"
        )
    return exported
