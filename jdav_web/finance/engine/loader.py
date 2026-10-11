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

import hashlib
import sys
from collections.abc import Mapping
from importlib.abc import Loader
from importlib.abc import MetaPathFinder
from importlib.machinery import ModuleSpec
from importlib.util import module_from_spec
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
    (:class:`RulesetInvalid`). ``check=False`` skips the whitelist, which is
    for the engine's own tests, never for stored sources.
    """
    if "__init__.py" not in sources:
        raise RulesetInvalid("a ruleset package needs an __init__.py")
    if check:
        problems = check_sources(sources)
        if problems:
            raise RulesetRejected(problems)
    package = package_name(sources)
    FINDER.register(package, sources)
    _install()
    module = sys.modules.get(package)
    if module is None:
        spec = FINDER.find_spec(package)
        assert spec is not None and spec.loader is not None
        module = module_from_spec(spec)
        sys.modules[package] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            del sys.modules[package]
            raise
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
