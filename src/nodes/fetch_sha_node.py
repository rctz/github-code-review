import logging

from services.github import GitHubService
from state.models import PRReviewState

logger = logging.getLogger(__name__)


def fetch_sha_node(state: PRReviewState) -> dict:
    """LangGraph node: fetch HEAD SHA, PR title, and PR body."""
    try:
        github_service = GitHubService(token=state.github_token or None)
        sha, title, body = github_service.fetch_pr_metadata(
            repo_name=state.repo_name,
            owner=state.owner,
            pr_id=int(state.pr_id),
        )
        return {"head_sha": sha, "pr_title": title, "pr_body": body}
    except Exception as exc:
        logger.error("Failed to fetch PR metadata for %s/%s#%s: %s", state.owner, state.repo_name, state.pr_id, exc)
        return {"error": str(exc)}
