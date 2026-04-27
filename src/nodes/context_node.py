import logging

from agents.context_selector import MAX_CONTEXT_FILES, run_context_selector
from prompts.dependency import DEPENDENCY_CONTEXT_TEMPLATE, NO_DEPENDENCIES_MESSAGE
from services.github import GitHubService
from state.models import SingleFileState

logger = logging.getLogger(__name__)

_CONTENT_TRUNCATE = 600


def context_node(state: SingleFileState) -> dict:
    """LangGraph node: select and fetch relevant context files for a file diff.

    Replaces dependency_node. Uses the repo file tree (fetched once by
    fetch_tree_node) and a lightweight LLM to pick the files most relevant
    to this diff, then fetches their content from GitHub.
    """
    if not state.diff or not state.repo_tree:
        return {"dependency_context": ""}

    try:
        github = GitHubService(token=state.github_token or None)
        full_repo = f"{state.owner}/{state.repo_name}"

        selected_paths = run_context_selector(
            filename=state.filename,
            diff=state.diff,
            repo_tree=state.repo_tree,
        )

        parts: list[str] = []
        for path in selected_paths[:MAX_CONTEXT_FILES]:
            content = github.fetch_file_content(full_repo, path, ref=state.head_sha)
            if not content.startswith("[Error"):
                parts.append(
                    DEPENDENCY_CONTEXT_TEMPLATE.format(
                        path=path,
                        content=content[:_CONTENT_TRUNCATE],
                    )
                )

        return {"dependency_context": "\n\n".join(parts) if parts else NO_DEPENDENCIES_MESSAGE}
    except Exception as exc:
        logger.error("context_node failed for %s: %s", state.filename, exc)
        return {"dependency_context": ""}
