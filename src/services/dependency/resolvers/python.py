"""Python dependency resolver with an extensible plugin interface."""

import re
from abc import ABC, abstractmethod
from pathlib import PurePosixPath

from services.dependency.base import _STDLIB_MODULES, DependencyResolver

_RE_FROM_MODULE = re.compile(r"^\+?\s*from\s+(\.+[\w.]*|[\w.]+)\s+import\s+\(?([^)]*)\)?")
_RE_DIRECT_IMPORT = re.compile(r"^\+?\s*import\s+([\w.]+)")
# Matches self.X.Y.method() chains — captures Y (e.g., "mission" from self.node.mission.pause())
# This finds runtime dependencies that are accessed via attributes, not imports.
_RE_ATTR_CHAIN = re.compile(r"\bself\.(?:\w+\.)+(\w+)\.\w+\(")


def _collapse_multiline_imports(content: str) -> list[str]:
    """Collapse multi-line parenthesized imports into single logical lines."""
    result: list[str] = []
    buffer: list[str] = []
    in_paren = False

    for line in content.splitlines():
        stripped = line.lstrip("+").lstrip()
        if not in_paren:
            if re.match(r"(?:from\s+[\w.]+\s+import|import\s+)\s*\(", stripped) and ")" not in stripped:
                in_paren = True
                buffer = [line]
            else:
                result.append(line)
        else:
            buffer.append(stripped)
            if ")" in stripped:
                in_paren = False
                result.append(" ".join(buffer))
                buffer = []

    result.extend(buffer)
    return result


class PythonImportPlugin(ABC):
    """Plugin interface for extending Python import resolution."""

    @abstractmethod
    def resolve(
        self,
        from_module: str | None,
        imported_items: str | None,
        direct_module: str | None,
        file_dir: PurePosixPath,
    ) -> list[str] | None:
        """Return candidate paths for this import, or None to defer to the next plugin."""


class PythonAttrPlugin(ABC):
    """Plugin interface for resolving attribute-access chains (e.g. self.node.mission.method())."""

    @abstractmethod
    def resolve_attr(self, attr_name: str, file_dir: PurePosixPath) -> list[str] | None:
        """Return additional candidate paths for this attribute, or None to skip."""


class PythonResolver(DependencyResolver):
    """Resolve Python import dependencies, with optional plugin extensions."""

    def __init__(
        self,
        plugins: list[PythonImportPlugin] | None = None,
        attr_plugins: list[PythonAttrPlugin] | None = None,
    ) -> None:
        self._plugins = plugins or []
        self._attr_plugins = attr_plugins or []

    def guess_paths(self, filename: str, content: str, repo_name: str) -> list[str]:
        file_dir = PurePosixPath(filename).parent
        seen: set[str] = set()
        candidates: list[str] = []

        def _add(path: str) -> None:
            if path not in seen:
                seen.add(path)
                candidates.append(path)

        for line in _collapse_multiline_imports(content):
            from_match = _RE_FROM_MODULE.match(line)
            direct_match = _RE_DIRECT_IMPORT.match(line)

            from_module = from_match.group(1) if from_match else None
            imported_items = from_match.group(2).strip() if from_match else None
            direct_module = direct_match.group(1) if direct_match else None

            plugin_handled = False
            for plugin in self._plugins:
                result = plugin.resolve(from_module, imported_items, direct_module, file_dir)
                if result is not None:
                    for p in result:
                        _add(p)
                    plugin_handled = True

            if plugin_handled:
                continue

            module = from_module or direct_module
            if not module:
                continue

            if module.startswith("."):
                dots = len(module) - len(module.lstrip("."))
                relative_part = module.lstrip(".")
                base = file_dir
                for _ in range(dots - 1):
                    base = base.parent
                path = str(base / relative_part.replace(".", "/")) if relative_part else str(base)
                _add(f"{path}.py")
                # When importing from a package (from .pkg import a, b), also try each
                # item as a submodule file inside the package directory.
                if relative_part and imported_items:
                    for item in imported_items.split(","):
                        name = item.strip().split(" as ")[0].strip()
                        if name and name != "*":
                            _add(f"{path}/{name}.py")
            else:
                root = module.split(".")[0]
                if root in _STDLIB_MODULES:
                    continue
                rel_path = module.replace(".", "/")
                _add(f"{rel_path}.py")
                # Also try relative to each ancestor directory of the importing file
                parts = file_dir.parts
                for i in range(len(parts)):
                    ancestor = str(PurePosixPath(*parts[: len(parts) - i]))
                    _add(f"{ancestor}/{rel_path}.py")

        # Scan added lines for attribute-access chains (e.g., self.node.mission.method())
        # to surface class files not reachable via explicit imports.
        for line in content.splitlines():
            if not line.startswith("+"):
                continue
            for match in _RE_ATTR_CHAIN.finditer(line):
                attr = match.group(1)
                _add(f"{file_dir}/{attr}.py")
                _add(f"{file_dir.parent}/{attr}.py")
                for plugin in self._attr_plugins:
                    result = plugin.resolve_attr(attr, file_dir)
                    if result:
                        for p in result:
                            _add(p)

        return candidates
