import logging
from pathlib import PurePosixPath

from agents.context_selector import run_context_selector
from agents.import_resolver import resolve_imports
from prompts.dependency import DEPENDENCY_CONTEXT_TEMPLATE, NO_DEPENDENCIES_MESSAGE
from services.github import GitHubService
from state.models import SingleFileState

logger = logging.getLogger(__name__)

# Total context budget: Layer 1 + Layer 2 combined
_MAX_TOTAL_CONTEXT_FILES = 12

# File-type-aware content limits
_FULL_CONTENT_TYPES = frozenset((".msg", ".srv", ".action", ".idl", ".proto", ".thrift"))
_SCHEMA_CONTENT_TYPES = frozenset((".yaml", ".yml", ".json", ".toml", ".xml"))
_SOURCE_CONTENT_LIMIT = 4000
_SCHEMA_CONTENT_LIMIT = 2000
_DEFAULT_CONTENT_LIMIT = 1500


def _truncate_by_type(path: str, content: str) -> str:
    """Return truncated content with a file-type-aware limit."""
    ext = PurePosixPath(path).suffix
    if ext in _FULL_CONTENT_TYPES:
        return content
    if ext in _SCHEMA_CONTENT_TYPES:
        return content[:_SCHEMA_CONTENT_LIMIT]
    # Source code files
    if ext in (
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".kts",
        ".cpp",
        ".cc",
        ".cxx",
        ".c",
        ".hpp",
        ".h",
        ".php",
        ".rb",
    ):
        return content[:_SOURCE_CONTENT_LIMIT]
    return content[:_DEFAULT_CONTENT_LIMIT]


def context_node(state: SingleFileState) -> dict:
    """LangGraph node: build dependency context via two-layer selection.

    Layer 1: Deterministic import resolution from diff lines (import_resolver).
    Layer 2: LLM-based semantic selection (context_selector) for remaining budget.
    """
    if not state.diff or not state.repo_tree:
        return {"dependency_context": ""}

    try:
        github = GitHubService(token=state.github_token or None)
        full_repo = f"{state.owner}/{state.repo_name}"

        # ---- Layer 1: deterministic import resolution ----
        layer1_paths = resolve_imports(
            filename=state.filename,
            diff=state.diff,
            repo_tree=state.repo_tree,
        )
        layer1_set = set(layer1_paths)

        # ---- Layer 2: LLM semantic selection with remaining budget ----
        remaining_budget = max(0, _MAX_TOTAL_CONTEXT_FILES - len(layer1_paths))
        layer2_paths: list[str] = []
        if remaining_budget > 0:
            layer2_paths = run_context_selector(
                filename=state.filename,
                diff=state.diff,
                repo_tree=state.repo_tree,
                exclude=layer1_set,
                max_files=remaining_budget,
            )

        # Combine: Layer 1 first (direct deps), then Layer 2 (semantic)
        selected_paths = list(dict.fromkeys(layer1_paths + layer2_paths))

        parts: list[str] = []
        for path in selected_paths[:_MAX_TOTAL_CONTEXT_FILES]:
            content = github.fetch_file_content(full_repo, path, ref=state.head_sha)
            if not content.startswith("[Error"):
                parts.append(
                    DEPENDENCY_CONTEXT_TEMPLATE.format(
                        path=path,
                        content=_truncate_by_type(path, content),
                    )
                )

        return {"dependency_context": "\n\n".join(parts) if parts else NO_DEPENDENCIES_MESSAGE}
    except Exception as exc:
        logger.error("context_node failed for %s: %s", state.filename, exc)
        return {"dependency_context": ""}
