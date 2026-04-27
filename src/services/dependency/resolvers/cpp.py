"""C/C++ dependency resolver."""

import re
from pathlib import PurePosixPath

from services.dependency.base import DependencyResolver

_RE_CPP_INCLUDE = re.compile(r'^\+\s*#include\s+([<"])(.+?)[>"]')


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
