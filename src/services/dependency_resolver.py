"""Strategy pattern registry for guessing dependency file paths."""

import re
from abc import ABC, abstractmethod
from pathlib import PurePosixPath

_STDLIB_MODULES: frozenset[str] = frozenset(
    {
        "abc",
        "argparse",
        "ast",
        "asyncio",
        "base64",
        "collections",
        "configparser",
        "contextlib",
        "copy",
        "csv",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "functools",
        "glob",
        "hashlib",
        "http",
        "importlib",
        "inspect",
        "io",
        "itertools",
        "json",
        "logging",
        "math",
        "multiprocessing",
        "operator",
        "os",
        "pathlib",
        "pickle",
        "platform",
        "pprint",
        "queue",
        "re",
        "secrets",
        "shutil",
        "signal",
        "socket",
        "sqlite3",
        "string",
        "struct",
        "subprocess",
        "sys",
        "tempfile",
        "textwrap",
        "threading",
        "time",
        "traceback",
        "typing",
        "unittest",
        "urllib",
        "uuid",
        "warnings",
        "weakref",
        "xml",
        "yaml",
        "zipfile",
    }
)

_RE_CPP_INCLUDE = re.compile(r'^\+\s*#include\s+([<"])(.+?)[>"]')
_RE_PY_IMPORT = re.compile(r'^\+\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))')


class DependencyResolver(ABC):
    """Strategy interface for guessing dependency file paths."""

    @abstractmethod
    def guess_paths(self, filename: str, content: str, repo_name: str) -> list[str]:
        """Return candidate file paths to fetch from the repository."""


class CppResolver(DependencyResolver):
    """Resolve C/C++ header dependencies from #include directives."""

    def guess_paths(self, filename: str, content: str, repo_name: str) -> list[str]:
        pkg_name = repo_name.rsplit("/", maxsplit=1)[-1] if "/" in repo_name else repo_name
        file_dir = str(PurePosixPath(filename).parent)
        if file_dir == ".":
            file_dir = ""

        seen: set[str] = set()
        candidates: list[str] = []

        for line in content.splitlines():
            match = _RE_CPP_INCLUDE.match(line)
            if not match:
                continue
            kind, header = match.group(1), match.group(2)
            if kind == '"':
                if file_dir:
                    candidates.append(f"{file_dir}/{header}")
                else:
                    candidates.append(header)
                candidates.append(f"include/{header}")
                candidates.append(f"include/{pkg_name}/{header}")
            else:
                candidates.append(f"include/{header}")
                candidates.append(f"include/{pkg_name}/{header}")

        return [c for c in dict.fromkeys(candidates) if c not in seen or seen.add(c) is None]  # type: ignore[func-returns-value]


class PythonResolver(DependencyResolver):
    """Resolve Python import dependencies by converting dotted imports to file paths."""

    def guess_paths(self, filename: str, content: str, repo_name: str) -> list[str]:
        seen: set[str] = set()
        candidates: list[str] = []

        for line in content.splitlines():
            match = _RE_PY_IMPORT.match(line)
            if not match:
                continue
            module = match.group(1) or match.group(2)
            if not module:
                continue
            root = module.split(".")[0]
            if root in _STDLIB_MODULES:
                continue

            parts = module.split(".")
            path = "/".join(parts)

            if path not in seen:
                seen.add(path)
                candidates.append(f"{path}.py")
                candidates.append(f"{path}/__init__.py")

        return candidates


RESOLVER_REGISTRY: dict[str, DependencyResolver] = {
    ".cpp": CppResolver(),
    ".cc": CppResolver(),
    ".cxx": CppResolver(),
    ".c": CppResolver(),
    ".hpp": CppResolver(),
    ".h": CppResolver(),
    ".py": PythonResolver(),
}


def get_resolver(filename: str) -> DependencyResolver | None:
    """Look up a resolver by file extension."""
    ext = PurePosixPath(filename).suffix
    return RESOLVER_REGISTRY.get(ext)
