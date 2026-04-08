import logging
import re

from prompts.dependency import DEPENDENCY_CONTEXT_TEMPLATE, NO_DEPENDENCIES_MESSAGE

logger = logging.getLogger(__name__)

LIMIT_IMPORT_CHECK = 7


def _extract_imported_files(diff: str) -> list[str]:
    """Parse diff for added import/require/include lines and extract file paths."""
    patterns = [
        r"^\+\s*(?:from|import)\s+([\w./]+)",
        r'^\+\s*(?:import|require)\s+["\'](.+?)["\']',
        r'^\+\s*#include\s+[<"](.+?)[>"]',
    ]
    files: list[str] = []
    for line in diff.splitlines():
        for pattern in patterns:
            match = re.match(pattern, line)
            if match:
                files.append(match.group(1))
    return list(set(files))


def run_dependency(diff: str) -> str:
    """Identify file dependencies from a diff and format context.

    Args:
        diff: The unified diff string.

    Returns:
        A dependency context string for the review prompt.
    """
    imported = _extract_imported_files(diff)
    if not imported:
        return NO_DEPENDENCIES_MESSAGE

    parts: list[str] = []
    for imp in imported[:LIMIT_IMPORT_CHECK]:
        path = imp.replace(".", "/") + ".py" if "." in imp and "/" not in imp else imp
        # TODO: Fetch actual file content via GitHubService
        content = ""
        parts.append(DEPENDENCY_CONTEXT_TEMPLATE.format(path=path, content=content[:500]))

    return "\n\n".join(parts)
