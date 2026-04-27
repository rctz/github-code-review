import json
import logging
from pathlib import PurePosixPath

from prompts.context_selector import CONTEXT_SELECTOR_PROMPT
from providers.factory import LLMFactory
from providers.models import LiteLLMModel

logger = logging.getLogger(__name__)

MAX_CONTEXT_FILES = 8
_MAX_TREE_LINES = 300


def _filter_tree(filename: str, tree: list[str]) -> list[str]:
    """Return paths in the same top-level package and same file extension.

    Limits to _MAX_TREE_LINES entries so the LLM prompt stays bounded.
    Falls back to extension-only filter if the top-level package produces
    no matches (e.g., file is at the repo root).
    """
    ext = PurePosixPath(filename).suffix
    parts = PurePosixPath(filename).parts
    top = parts[0] if len(parts) > 1 else ""

    if top:
        related = [p for p in tree if p.startswith(top + "/") and p.endswith(ext)]
    else:
        related = [p for p in tree if p.endswith(ext)]

    return related[:_MAX_TREE_LINES]


def run_context_selector(
    filename: str,
    diff: str,
    repo_tree: list[str],
) -> list[str]:
    """Use a lightweight LLM to select relevant files from the repo tree.

    Returns a list of file paths (subset of repo_tree) to fetch as context.
    Returns an empty list if the tree is empty or the LLM response can't be parsed.
    """
    filtered = _filter_tree(filename, repo_tree)
    if not filtered:
        logger.debug("context_selector: no tree candidates for %s", filename)
        return []

    llm = LLMFactory.create(model=LiteLLMModel.CLAUDE_SONNET_4_6, temperature=0)
    prompt = CONTEXT_SELECTOR_PROMPT.format(
        filename=filename,
        diff=diff,
        file_list="\n".join(filtered),
        max_files=MAX_CONTEXT_FILES,
    )

    try:
        response = llm.chat(message=prompt)
        text = response.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        selected: list[str] = json.loads(text)
        valid = [p for p in selected if isinstance(p, str) and p in set(repo_tree)]
        logger.info(
            "context_selector selected %d/%d files for %s",
            len(valid),
            len(filtered),
            filename,
        )
        return valid
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("context_selector parse error for %s: %s", filename, exc)
        return []
