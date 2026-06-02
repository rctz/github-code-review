import json
import logging
from pathlib import PurePosixPath

from prompts.context_selector import CONTEXT_SELECTOR_PROMPT
from providers.factory import LLMFactory
from providers.models import LiteLLMModel

logger = logging.getLogger(__name__)

MAX_CONTEXT_FILES = 8
_MAX_TREE_LINES = 300


def _filter_tree(filename: str, tree: list[str], exclude: set[str] | None = None) -> list[str]:
    """Return paths in the same parent directory tree and same file extension.

    Uses the file's parent directory (not just top-level) for tighter scoping.
    Limits to _MAX_TREE_LINES entries so the LLM prompt stays bounded.
    Falls back to extension-only filter scoped by parent dir prefix.
    """
    ext = PurePosixPath(filename).suffix
    parent = str(PurePosixPath(filename).parent)
    exclude = exclude or set()

    if parent and parent != ".":
        # Filter by parent directory prefix + same extension, excluding known paths
        related = [p for p in tree if p.startswith(parent + "/") and p.endswith(ext) and p not in exclude]
    else:
        related = [p for p in tree if p.endswith(ext) and p not in exclude]

    # If parent dir filter is too restrictive, fall back to top-level component
    if not related and parent:
        top = PurePosixPath(filename).parts[0] if len(PurePosixPath(filename).parts) > 1 else ""
        if top:
            related = [p for p in tree if p.startswith(top + "/") and p.endswith(ext) and p not in exclude]

    # Final fallback: same extension anywhere in repo
    if not related:
        related = [p for p in tree if p.endswith(ext) and p not in exclude]

    return related[:_MAX_TREE_LINES]


def run_context_selector(
    filename: str,
    diff: str,
    repo_tree: list[str],
    exclude: set[str] | None = None,
    max_files: int | None = None,
) -> list[str]:
    """Use a lightweight LLM to select relevant files from the repo tree.

    Returns a list of file paths (subset of repo_tree) to fetch as context.
    Returns an empty list if the tree is empty or the LLM response can't be parsed.

    Args:
        exclude: Paths already resolved by Layer 1 (import_resolver) to avoid duplication.
        max_files: Override default MAX_CONTEXT_FILES (e.g. remaining budget).
    """
    exclude = exclude or set()
    filtered = _filter_tree(filename, repo_tree, exclude)
    if not filtered:
        logger.debug("context_selector: no tree candidates for %s", filename)
        return []

    budget = max_files if max_files is not None else MAX_CONTEXT_FILES
    llm = LLMFactory.create(model=LiteLLMModel.CLAUDE_SONNET_4_6, temperature=0)
    prompt = CONTEXT_SELECTOR_PROMPT.format(
        filename=filename,
        diff=diff,
        file_list="\n".join(filtered),
        max_files=budget,
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
