import logging

from services.github import GitHubService
from state.models import PRReviewState

logger = logging.getLogger(__name__)


def fetch_tree_node(state: PRReviewState) -> dict:
    """LangGraph node: fetch the full repository file tree at the PR head SHA.

    Runs once per PR review (before fan-out). Stores all blob paths in
    state.repo_tree so every parallel context_node can filter and select
    relevant files without making additional tree API calls.
    """
    try:
        github = GitHubService(token=state.github_token or None)
        full_repo = f"{state.owner}/{state.repo_name}"
        tree = github.fetch_repo_tree(full_repo, state.head_sha)
        return {"repo_tree": tree}
    except Exception as exc:
        logger.error("fetch_tree_node failed: %s", exc)
        return {"repo_tree": []}
