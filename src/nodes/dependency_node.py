import logging

from agents.dependency import run_dependency
from services.github import GitHubService
from state.models import SingleFileState

logger = logging.getLogger(__name__)


def dependency_node(state: SingleFileState) -> dict:
    """LangGraph node: resolve and fetch dependency context for a file diff."""
    if not state.diff:
        return {"dependency_context": ""}

    try:
        github_service = GitHubService(token=state.github_token or None)
        full_repo = f"{state.owner}/{state.repo_name}"
        context = run_dependency(
            filename=state.filename,
            diff=state.diff,
            repo_name=full_repo,
            head_sha=state.head_sha,
            github_service=github_service,
        )
        return {"dependency_context": context}
    except Exception as exc:
        logger.error("Dependency node failed for %s: %s", state.filename, exc)
        return {"dependency_context": ""}
