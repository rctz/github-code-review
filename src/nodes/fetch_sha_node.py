import logging

from services.github import GitHubService
from state.models import PRReviewState

logger = logging.getLogger(__name__)


def fetch_sha_node(state: PRReviewState) -> dict:
    """LangGraph node: fetch the HEAD commit SHA for the PR."""
    try:
        github_service = GitHubService(token=state.github_token or None)
        sha = github_service.fetch_pr_head_sha(
            repo_name=state.repo_name,
            owner=state.owner,
            pr_id=int(state.pr_id),
        )
        return {"head_sha": sha}
    except Exception as exc:
        logger.error("Failed to fetch HEAD SHA for %s/%s#%s: %s", state.owner, state.repo_name, state.pr_id, exc)
        return {"error": str(exc)}
