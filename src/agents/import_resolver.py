"""Multi-language import resolver: extract imports from diff lines and match against repo_tree."""

import logging
import re
from abc import ABC, abstractmethod
from pathlib import PurePosixPath

logger = logging.getLogger(__name__)

# ---- Regex patterns ----

# Python
_RE_PY_FROM = re.compile(r"^\+?\s*from\s+(\.+[\w.]*|[\w.]+)\s+import\s+(.+)$")
_RE_PY_IMPORT = re.compile(r"^\+?\s*import\s+([\w.]+(?:\s*,\s*[\w.]+)*)\b")

# JavaScript / TypeScript
_RE_JS_IMPORT = re.compile(r"^\+?\s*(?:import|export)\b.*?\bfrom\s+['\"]([^'\"]+)['\"]")
_RE_JS_REQUIRE = re.compile(r"^\+?\s*(?:const|let|var)\s+.*?=\s*require\(['\"]([^'\"]+)['\"]\)")
_RE_JS_DYNAMIC = re.compile(r"^\+?.*(?:await\s+)?import\(['\"]([^'\"]+)['\"]\)")

# Go
_RE_GO_IMPORT_SINGLE = re.compile(r"^\+?\s*import\s+(?:\w+\s+)?\"([^\"]+)\"")
_RE_GO_IMPORT_BLOCK = re.compile(r"^\+?\s*import\s+\(")
_RE_GO_IMPORT_LINE = re.compile(r"^\+?\s*(?:\w+\s+)?\"([^\"]+)\"")

# Java / Kotlin
_RE_JAVA_IMPORT = re.compile(r"^\+?\s*import\s+(?:static\s+)?([^\s;]+)\s*;?$")

# Rust
_RE_RUST_USE = re.compile(r"^\+?\s*use\s+([\w:]+(?:::\{[^}]+\})?)\s*;")
_RE_RUST_MOD = re.compile(r"^\+?\s*mod\s+(\w+)\s*;")

# C / C++
_RE_CPP_INCLUDE = re.compile(r"^\+?\s*#include\s+([\"<])(.+?)[\">]")

# PHP
_RE_PHP_USE = re.compile(r"^\+?\s*use\s+([\w\\]+(?:\\{[^}]+\})?)\s*;")
_RE_PHP_REQUIRE = re.compile(r"^\+?\s*(?:require|include)(?:_once)?\s+['\"]([^'\"]+)['\"]")

# Ruby
_RE_RUBY_REQUIRE_REL = re.compile(r"^\+?\s*require_relative\s+['\"]([^'\"]+)['\"]")
_RE_RUBY_REQUIRE = re.compile(r"^\+?\s*require\s+['\"]([^'\"]+)['\"]")

# ---- Stdlib skip sets ----

_STDLIB_GO: frozenset[str] = frozenset(
    "bufio bytes compress container context crypto database encoding errors expvar "
    "fmt hash image io log math mime net os path plugin reflect regexp runtime "
    "sort strconv strings sync syscall testing text time unicode unsafe".split()
)

_STDLIB_JAVA: frozenset[str] = frozenset()
# We skip by prefix matching: java.*, javax.*, kotlin.*, android.*

_STDLIB_RUST: frozenset[str] = frozenset(("std", "core", "alloc"))

# ROS2 interface types
_ROS2_TYPES: frozenset[str] = frozenset({"msg", "srv", "action", "idl"})

# ---- Suffix matching ----


def _match_suffix(suffix: str, repo_tree: list[str]) -> list[str]:
    """Find paths in repo_tree that end with the given suffix."""
    return [p for p in repo_tree if p == suffix or p.endswith("/" + suffix)]


def _strip_diff_prefix(line: str) -> str | None:
    """Strip diff prefix char (+, -, space) from a unified-diff line.

    Returns None for metadata/hunk lines that should be skipped:
    ---, +++, @@, backslash-escaped metadata
    """
    if line.startswith(("--- ", "+++ ", "@@ ", "\\ ")):
        return None
    if line and line[0] in " +-":
        return line[1:]
    return line


# ---- Extractor base class ----


class LanguageExtractor(ABC):
    """Extract imports/dependencies from diff lines for one language."""

    @abstractmethod
    def extract(self, diff: str) -> list[tuple[str, list[str]]]:
        """
        Return a list of (module_path, [imported_names]) from the diff.
        `module_path` is the raw import string (e.g. './components/Button').
        `imported_names` may be empty for direct-style imports.
        """

    def to_repo_paths(self, raw_imports: list[tuple[str, list[str]]], filename: str, repo_tree: list[str]) -> list[str]:
        """
        Convert raw imports to actual repo_tree paths.
        Default: treat each raw import as a suffix and match.
        Override for language-specific path resolution.
        """
        results: list[str] = []
        for raw, _ in raw_imports:
            results.extend(_match_suffix(raw, repo_tree))
        return results


# ---- Python ----


class _PythonExtractor(LanguageExtractor):
    def extract(self, diff: str) -> list[tuple[str, list[str]]]:
        results: list[tuple[str, list[str]]] = []
        for line in diff.splitlines():
            stripped = _strip_diff_prefix(line)
            if stripped is None:
                continue
            m = _RE_PY_FROM.match(stripped)
            if m:
                module = m.group(1).strip()
                names_str = m.group(2).strip()
                names = [
                    n.strip().split(" as ")[0].strip() for n in names_str.split(",") if n.strip() and n.strip() != "*"
                ]
                results.append((module, names))
                continue
            m = _RE_PY_IMPORT.match(stripped)
            if m:
                for mod in m.group(1).split(","):
                    mod = mod.strip()
                    if mod:
                        results.append((mod, []))
        return results

    def to_repo_paths(self, raw_imports: list[tuple[str, list[str]]], filename: str, repo_tree: list[str]) -> list[str]:
        file_dir = PurePosixPath(filename).parent
        repo_tree_set = set(repo_tree)
        results: list[str] = []

        for module, names in raw_imports:
            candidates = self._resolve(module, names, file_dir, repo_tree)
            for c in candidates:
                if c in repo_tree_set:
                    results.append(c)
                    continue
                # Try suffix match for workspace-prefixed paths
                for p in repo_tree:
                    if p.endswith("/" + c):
                        results.append(p)
                        break

        return list(dict.fromkeys(results))

    def _resolve(self, module: str, names: list[str], file_dir: PurePosixPath, repo_tree: list[str]) -> list[str]:
        candidates: list[str] = []

        if module.startswith("."):
            # Relative import
            dots = len(module) - len(module.lstrip("."))
            relative_part = module.lstrip(".")
            base = file_dir
            for _ in range(dots - 1):
                base = base.parent
            base_str = str(base)

            if relative_part:
                rel_path = relative_part.replace(".", "/")
                candidates.append(f"{base_str}/{rel_path}.py")
                candidates.append(f"{base_str}/{rel_path}/__init__.py")
                for name in names:
                    candidates.append(f"{base_str}/{rel_path}/{name}.py")
                # Also try bare relative path (for non-workspace repos)
                candidates.append(f"{rel_path}.py")
                candidates.append(f"{rel_path}/__init__.py")
            else:
                # e.g., "from . import sibling"  -- resolve names in current dir
                candidates.append(f"{base_str}/__init__.py")
                for name in names:
                    candidates.append(f"{base_str}/{name}.py")
                    candidates.append(f"{base_str}/{name}/__init__.py")
                for name in names:
                    candidates.append(f"{name}.py")
                    candidates.append(f"{name}/__init__.py")

            # Match against repo_tree to find the actual prefix
            actual_prefixes = self._find_dir_prefixes(base_str, repo_tree)
            for prefix in actual_prefixes:
                if relative_part:
                    rel = relative_part.replace(".", "/")
                    candidates.append(f"{prefix}/{rel}.py")
                    candidates.append(f"{prefix}/{rel}/__init__.py")
                    for name in names:
                        candidates.append(f"{prefix}/{rel}/{name}.py")
                else:
                    for name in names:
                        candidates.append(f"{prefix}/{name}.py")
                        candidates.append(f"{prefix}/{name}/__init__.py")
        else:
            root = module.split(".")[0]
            if root in _PYTHON_STDLIB:
                return []

            rel_path = module.replace(".", "/")
            # Direct candidates
            candidates.append(f"{rel_path}.py")
            candidates.append(f"{rel_path}/__init__.py")
            for name in names:
                candidates.append(f"{rel_path}/{name}.py")
                candidates.append(f"{rel_path}/{name}.pyi")  # type stub

            # ROS2 interface variants
            parts = module.split(".")
            if parts and parts[-1] in _ROS2_TYPES and names:
                interface_type = parts[-1]
                pkg_path = "/".join(parts[:-1])
                for name in names:
                    candidates.append(f"{pkg_path}/{interface_type}/{name}.{interface_type}")

            # Try matching against repo_tree (find actual nesting prefix)
            for suffix in [f"{rel_path}.py", f"{rel_path}/__init__.py"]:
                for path in repo_tree:
                    if path.endswith("/" + suffix):
                        # Try sibling deps relative to found path
                        found_prefix = path[: -len("/" + suffix)]
                        for name in names:
                            candidates.append(f"{found_prefix}/{rel_path}/{name}.py")

        return candidates

    def _find_dir_prefixes(self, base_str: str, repo_tree: list[str]) -> list[str]:
        """Find repo_tree paths that contain the given directory."""
        # Try exact match first
        exact = [p for p in repo_tree if p == base_str or "/" + base_str in p]
        if exact:
            return list(
                dict.fromkeys(p[: p.rfind("/" + base_str) + len("/" + base_str)] for p in exact if "/" + base_str in p)
            )
        # Fallback: match last-segment of base_str
        last = base_str.split("/")[-1]
        return list(dict.fromkeys(p[: p.rfind("/" + last) + len("/" + last)] for p in repo_tree if "/" + last in p))


# Python stdlib heuristic (common modules)
_PYTHON_STDLIB: frozenset[str] = frozenset(
    "abc argparse asyncio base64 bisect builtins calendar collections contextlib copy csv ctypes"
    " dataclasses datetime decimal enum errno faulthandler filecmp fnmatch fractions functools"
    " gc glob hashlib heapq html http inspect io itertools json locale logging math mimetypes"
    " multiprocessing numbers operator os pathlib pickle platform posix pprint queue random re"
    " signal socket sqlite3 ssl stat string struct subprocess sys tempfile textwrap threading"
    " time traceback typing unittest urllib uuid warnings xml zipfile zlib".split()
    + "typing_extensions numpy scipy pandas matplotlib sklearn torch tensorflow django flask fastapi".split()
    + "pytest unittest mock pydantic requests urllib3 httpx aiohttp celery kombu redis".split()
    + "deepwiki sourcegraph langgraph langchain openai anthropic litellm".split()
)


# ---- JavaScript / TypeScript ----


class _JSExtractor(LanguageExtractor):
    _EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")

    def extract(self, diff: str) -> list[tuple[str, list[str]]]:
        results: list[tuple[str, list[str]]] = []
        for line in diff.splitlines():
            stripped = _strip_diff_prefix(line)
            if stripped is None:
                continue
            for pattern in (_RE_JS_IMPORT, _RE_JS_REQUIRE, _RE_JS_DYNAMIC):
                m = pattern.match(stripped)
                if m:
                    path = m.group(1)
                    if not path.startswith(".") and "/" not in path and "@" not in path:
                        continue  # skip bare npm packages
                    results.append((path, []))
                    break
        return results

    def to_repo_paths(self, raw_imports: list[tuple[str, list[str]]], filename: str, repo_tree: list[str]) -> list[str]:
        file_dir = PurePosixPath(filename).parent
        results: list[str] = []
        repo_tree_set = set(repo_tree)

        for raw, _ in raw_imports:
            candidates = self._make_candidates(raw, file_dir, repo_tree_set)
            for c in candidates:
                if c in repo_tree_set:
                    results.append(c)

        return list(dict.fromkeys(results))

    def _make_candidates(self, raw: str, file_dir: PurePosixPath, repo_tree_set: set[str]) -> list[str]:
        candidates: list[str] = []

        if raw.startswith("./") or raw.startswith("../"):
            base = file_dir / raw
            base_str = str(base)

            for ext in self._EXTENSIONS:
                candidates.append(base_str + ext)

            # index file
            for ext in self._EXTENSIONS:
                if not base_str.endswith("/"):
                    candidates.append(base_str + "/index" + ext)
                else:
                    candidates.append(base_str + "index" + ext)

        elif raw.startswith("@/"):
            # Alias: @/ → src/
            rest = raw[2:]
            for prefix in ("src", "lib", "app"):
                candidates.append(f"{prefix}/{rest}.ts")
                candidates.append(f"{prefix}/{rest}.tsx")
                candidates.append(f"{prefix}/{rest}.js")
                candidates.append(f"{prefix}/{rest}/index.ts")
                candidates.append(f"{prefix}/{rest}/index.tsx")

        elif "/" in raw:
            # Scoped package or relative-like path: try as-is with extensions
            for ext in self._EXTENSIONS:
                candidates.append(f"{raw}{ext}")
            for ext in self._EXTENSIONS:
                candidates.append(f"{raw}/index{ext}")

        return candidates


# ---- Go ----


class _GoExtractor(LanguageExtractor):
    def extract(self, diff: str) -> list[tuple[str, list[str]]]:
        results: list[tuple[str, list[str]]] = []
        in_block = False
        for line in diff.splitlines():
            stripped = _strip_diff_prefix(line)
            if stripped is None:
                continue

            if _RE_GO_IMPORT_BLOCK.match(stripped):
                in_block = True
                continue
            if in_block and stripped.strip() == ")":
                in_block = False
                continue

            m = _RE_GO_IMPORT_SINGLE.match(stripped)
            if m or (in_block and (m := _RE_GO_IMPORT_LINE.match(stripped))):
                path = m.group(1)
                if "/" not in path:
                    continue  # stdlib single import
                if path.split("/")[-1] in _STDLIB_GO:
                    continue
                results.append((path, []))
        return results

    def to_repo_paths(self, raw_imports: list[tuple[str, list[str]]], filename: str, repo_tree: list[str]) -> list[str]:
        results: list[str] = []
        repo_tree_set = set(repo_tree)

        for raw, _ in raw_imports:
            # Go import paths map to directories, and the file imports everything in that dir.
            # Extract last segments: "github.com/org/repo/pkg/util" -> "pkg/util"
            parts = raw.split("/")
            # Try progressively shorter suffix matches
            for i in range(1, min(len(parts), 4)):
                suffix = "/".join(parts[-i:])
                for p in repo_tree:
                    if p.endswith("/" + suffix) or p == suffix:
                        # Found directory match - include .go files under it
                        if p.endswith(".go"):
                            results.append(p)
                        elif p in repo_tree_set:
                            # It's a directory path in repo_tree (unlikely, tree lists files)
                            pass

            # Suffix match for .go files under identified directories
            for suffix in (
                (parts[-1] + ".go", f"{parts[-2] if len(parts) > 1 else parts[-1]}.go")
                if len(parts) > 1
                else (parts[-1] + ".go",)
            ):
                for p in repo_tree:
                    if p.endswith("/" + suffix):
                        results.append(p)

        return list(dict.fromkeys(results))


# ---- Java / Kotlin ----


class _JavaExtractor(LanguageExtractor):
    _SKIP_PREFIXES = ("java.", "javax.", "kotlin.", "kotlinx.", "android.", "org.springframework.", "org.jetbrains.")

    def extract(self, diff: str) -> list[tuple[str, list[str]]]:
        results: list[tuple[str, list[str]]] = []
        for line in diff.splitlines():
            stripped = _strip_diff_prefix(line)
            if stripped is None:
                continue
            m = _RE_JAVA_IMPORT.match(stripped)
            if m:
                pkg = m.group(1)
                if any(pkg.startswith(p) for p in self._SKIP_PREFIXES):
                    continue
                results.append((pkg, []))
        return results

    def to_repo_paths(self, raw_imports: list[tuple[str, list[str]]], filename: str, repo_tree: list[str]) -> list[str]:
        results: list[str] = []

        for raw, _ in raw_imports:
            parts = raw.split(".")
            is_wildcard = raw.endswith(".*")
            if is_wildcard:
                parts = parts[:-1]  # drop "*"

            if is_wildcard:
                dir_suffix = "/".join(parts)
                for p in repo_tree:
                    prefix_match = p.rfind("/" + dir_suffix + "/")
                    if prefix_match >= 0 or p.startswith(dir_suffix + "/"):
                        results.append(p)
            else:
                # Try class filename match
                class_name = parts[-1]
                path_suffix = "/".join(parts)

                for ext in (".java", ".kt", ".scala"):
                    # Direct match: com/example/Foo.java
                    for p in repo_tree:
                        if p.endswith("/" + path_suffix + ext):
                            results.append(p)
                            break
                    else:
                        # Match class name only
                        for p in repo_tree:
                            if p.endswith("/" + class_name + ext):
                                results.append(p)
                                break

                # Also try as directory path for Kotlin object files
                for p in repo_tree:
                    if p.endswith("/" + path_suffix + ".kt") or p.endswith("/" + path_suffix + ".kts"):
                        results.append(p)

        return list(dict.fromkeys(results))


# ---- Rust ----


class _RustExtractor(LanguageExtractor):
    def extract(self, diff: str) -> list[tuple[str, list[str]]]:
        results: list[tuple[str, list[str]]] = []
        for line in diff.splitlines():
            stripped = _strip_diff_prefix(line)
            if stripped is None:
                continue
            m = _RE_RUST_USE.match(stripped)
            if m:
                path = m.group(1)
                if any(path.startswith(p + "::") for p in _STDLIB_RUST) or path in _STDLIB_RUST:
                    continue
                results.append((path, []))
                continue
            m = _RE_RUST_MOD.match(stripped)
            if m:
                results.append(("mod:" + m.group(1), []))
        return results

    def to_repo_paths(self, raw_imports: list[tuple[str, list[str]]], filename: str, repo_tree: list[str]) -> list[str]:
        file_dir = PurePosixPath(filename).parent
        results: list[str] = []
        repo_tree_set = set(repo_tree)

        for raw, _ in raw_imports:
            if raw.startswith("mod:"):
                mod_name = raw[4:]
                for candidate in (
                    f"{file_dir}/{mod_name}.rs",
                    f"{file_dir}/{mod_name}/mod.rs",
                ):
                    if candidate in repo_tree_set:
                        results.append(candidate)
                continue

            # Strip use group: crate::foo::{bar, baz} -> crate::foo
            path = raw.split("::{")[0]
            parts = path.split("::")

            if parts[0] == "crate":
                # crate::services::auth -> services/auth.rs or services/auth/mod.rs
                rel = "/".join(parts[1:])
                candidates = [f"{rel}.rs", f"{rel}/mod.rs"]
            elif parts[0] == "super":
                # super::foo -> parent_dir/foo.rs
                parent = str(file_dir.parent)
                rel = "/".join(parts[1:])
                candidates = [f"{parent}/{rel}.rs", f"{parent}/{rel}/mod.rs"] if rel else []
            else:
                # External crate — skip for now
                continue

            for c in candidates:
                for p in repo_tree:
                    if p.endswith("/" + c) or p == c:
                        if p in repo_tree_set:
                            results.append(p)
                            break

        return list(dict.fromkeys(results))


# ---- C / C++ ----


class _CppExtractor(LanguageExtractor):
    def extract(self, diff: str) -> list[tuple[str, list[str]]]:
        results: list[tuple[str, list[str]]] = []
        for line in diff.splitlines():
            stripped = _strip_diff_prefix(line)
            if stripped is None:
                continue
            m = _RE_CPP_INCLUDE.match(stripped)
            if m:
                kind, header = m.group(1), m.group(2)
                if kind == "<":
                    continue  # system header
                results.append((header, []))
        return results

    def to_repo_paths(self, raw_imports: list[tuple[str, list[str]]], filename: str, repo_tree: list[str]) -> list[str]:
        file_dir = str(PurePosixPath(filename).parent)
        if file_dir == ".":
            file_dir = ""

        results: list[str] = []
        repo_tree_set = set(repo_tree)

        for raw, _ in raw_imports:
            candidates: list[str] = []
            if file_dir:
                candidates.append(f"{file_dir}/{raw}")
            candidates.append(raw)

            base = raw
            if not raw.endswith(".h") and not raw.endswith(".hpp"):
                for ext in (".h", ".hpp"):
                    candidates.append(base + ext)

            # Try include/ prefixed
            candidates.append(f"include/{raw}")
            if not raw.endswith(".h"):
                candidates.append(f"include/{raw}.h")
                candidates.append(f"include/{raw}.hpp")

            for c in candidates:
                if c in repo_tree_set:
                    results.append(c)

        return list(dict.fromkeys(results))


# ---- PHP ----


class _PHPExtractor(LanguageExtractor):
    _SKIP_PREFIXES = (
        "Illuminate\\",
        "Symfony\\",
        "Doctrine\\",
        "Laravel\\",
        "PHPUnit\\",
        "Composer\\",
        "Psr\\",
    )
    # Note: "App\\" and "Src\\" are intentionally NOT here — they are
    # the user's own namespaces and should be resolved to local files.

    def extract(self, diff: str) -> list[tuple[str, list[str]]]:
        results: list[tuple[str, list[str]]] = []
        for line in diff.splitlines():
            stripped = _strip_diff_prefix(line)
            if stripped is None:
                continue
            m = _RE_PHP_USE.match(stripped)
            if m:
                ns = m.group(1)
                # Known framework skip
                if any(ns.startswith(p) for p in self._SKIP_PREFIXES):
                    continue
                results.append((ns, []))
                continue
            m = _RE_PHP_REQUIRE.match(stripped)
            if m:
                path = m.group(1)
                results.append((path, []))
        return results

    def to_repo_paths(self, raw_imports: list[tuple[str, list[str]]], filename: str, repo_tree: list[str]) -> list[str]:
        file_dir = PurePosixPath(filename).parent
        results: list[str] = []
        repo_tree_set = set(repo_tree)

        for raw, _ in raw_imports:
            is_file_path = raw.endswith(".php") or raw.startswith((".", "/"))
            if is_file_path:
                # Relative require/include path
                if not raw.startswith("/"):
                    resolved = str(file_dir / raw)
                else:
                    resolved = raw.lstrip("/")
                if resolved in repo_tree_set:
                    results.append(resolved)
                for p in repo_tree:
                    if p.endswith("/" + raw):
                        results.append(p)
                continue

            # Namespace: App\Service\User -> app/Service/User.php or src/Service/User.php
            ns_parts = raw.split("\\")
            possible_roots: list[str] = []

            # Try stripping common root namespace
            for root in ("App", "app", "Src", "src", ns_parts[0]):
                if raw.startswith(root + "\\"):
                    rest = raw[len(root) + 1 :]
                    for prefix in ("app", "src", "lib"):
                        possible_roots.append(f"{prefix}/{rest.replace('\\', '/')}")
                    break
            else:
                # No matching root: try all common prefixes
                rel = raw.replace("\\", "/")
                for prefix in ("app", "src", "lib"):
                    possible_roots.append(f"{prefix}/{rel}")
                possible_roots.append(rel)

            class_name = ns_parts[-1]
            for base in possible_roots:
                for ext in (".php", ".php.inc"):
                    candidates = [base + ext]
                    # Also try just the class name in the directory
                    dir_path = "/".join(base.split("/")[:-1])
                    if dir_path:
                        candidates.append(f"{dir_path}/{class_name}{ext}")

                    for c in candidates:
                        for p in repo_tree:
                            if p.endswith("/" + c) or p == c:
                                if p in repo_tree_set:
                                    results.append(p)
                                    break

        return list(dict.fromkeys(results))


# ---- Ruby ----


class _RubyExtractor(LanguageExtractor):
    def extract(self, diff: str) -> list[tuple[str, list[str]]]:
        results: list[tuple[str, list[str]]] = []
        for line in diff.splitlines():
            stripped = _strip_diff_prefix(line)
            if stripped is None:
                continue
            m = _RE_RUBY_REQUIRE_REL.match(stripped)
            if m:
                results.append((m.group(1), []))
                continue
            m = _RE_RUBY_REQUIRE.match(stripped)
            if m:
                path = m.group(1)
                # Skip bare stdlib gems
                if "/" not in path and "." not in path and len(path) < 20:
                    continue
                results.append((path, []))
        return results

    def to_repo_paths(self, raw_imports: list[tuple[str, list[str]]], filename: str, repo_tree: list[str]) -> list[str]:
        file_dir = PurePosixPath(filename).parent
        results: list[str] = []
        repo_tree_set = set(repo_tree)

        for raw, _ in raw_imports:
            is_relative = not raw.startswith("/") and ("/" in raw or raw.startswith("."))

            if is_relative:
                # Normalize .. and . segments manually
                import posixpath

                raw_path = posixpath.normpath(str(file_dir / raw))
                candidate = raw_path.lstrip("/")
                if not candidate.endswith(".rb"):
                    candidate += ".rb"
                if candidate in repo_tree_set:
                    results.append(candidate)
                    continue

            # Also try as-is with .rb extension
            candidate = raw if raw.endswith(".rb") else raw + ".rb"
            if candidate in repo_tree_set:
                results.append(candidate)
                continue

            # Try suffix match
            suffix = candidate
            for p in repo_tree:
                if p.endswith("/" + suffix) or p == suffix:
                    results.append(p)

        return list(dict.fromkeys(results))


# ---- Dispatch table ----

_EXTRACTORS: dict[str, LanguageExtractor] = {
    ".py": _PythonExtractor(),
    ".ts": _JSExtractor(),
    ".tsx": _JSExtractor(),
    ".js": _JSExtractor(),
    ".jsx": _JSExtractor(),
    ".mjs": _JSExtractor(),
    ".cjs": _JSExtractor(),
    ".go": _GoExtractor(),
    ".java": _JavaExtractor(),
    ".kt": _JavaExtractor(),
    ".kts": _JavaExtractor(),
    ".rs": _RustExtractor(),
    ".php": _PHPExtractor(),
    ".rb": _RubyExtractor(),
    ".cpp": _CppExtractor(),
    ".cc": _CppExtractor(),
    ".cxx": _CppExtractor(),
    ".c": _CppExtractor(),
    ".hpp": _CppExtractor(),
    ".h": _CppExtractor(),
}


# ---- Public interface ----


def resolve_imports(filename: str, diff: str, repo_tree: list[str]) -> list[str]:
    """
    Return a list of repo_tree paths that are direct imports/dependencies
    of the changed file, matched from diff +lines.
    """
    ext = PurePosixPath(filename).suffix
    extractor = _EXTRACTORS.get(ext)
    if not extractor:
        logger.debug("No import extractor for extension %s (%s)", ext, filename)
        return []

    raw = extractor.extract(diff)
    if not raw:
        return []

    resolved = extractor.to_repo_paths(raw, filename, repo_tree)
    logger.debug("Resolved %d imports for %s -> %d paths", len(raw), filename, len(resolved))
    return resolved
