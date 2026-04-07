import re

from dotenv import load_dotenv

from providers.litellm import LiteLLM, LiteLLMModel

load_dotenv()

LIMIT_IMPORT_CHECK = 7


def _get_llm() -> LiteLLM:
    return LiteLLM(model=LiteLLMModel.CLAUDE_SONNET_4_6, temperature=0.8)


def _extract_imported_files(diff: str) -> list[str]:
    """Parse diff for added import/require/include lines and extract file paths."""
    patterns = [
        r"^\+\s*(?:from|import)\s+([\w./]+)",  # Python: from x import / import x
        r'^\+\s*(?:import|require)\s+["\'](.+?)["\']',  # JS/TS
        r'^\+\s*#include\s+[<"](.+?)[>"]',  # C/C++
    ]
    files: list[str] = []
    for line in diff.splitlines():
        for pattern in patterns:
            match = re.match(pattern, line)
            if match:
                files.append(match.group(1))
    return list(set(files))


def run_dependency(diff: str) -> str:
    """Identify file dependencies from a diff and fetch their content for context.

    Returns:
        A dependency context string to be included in the review prompt.
    """
    imported = _extract_imported_files(diff)

    if not imported:
        return "No external dependencies detected in this diff."

    fetched_parts: list[str] = []
    for imp in imported[:LIMIT_IMPORT_CHECK]:  # limit files to control token usage
        path = imp.replace(".", "/") + ".py" if "." in imp and "/" not in imp else imp
        # content = fetch_file_content(repo_name, path)
        content = ""
        fetched_parts.append(f"### {path}\n```\n{content[:500]}\n```")

    return "\n\n".join(fetched_parts)
