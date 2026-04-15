import logging

from agents.review import FileReviewOutput
from services.github import GitHubService
from state.models import PRReviewState

logger = logging.getLogger(__name__)


def post_review_node(state: PRReviewState) -> dict:
    """LangGraph node: post one comment per file review to GitHub.

    Each file gets its own top-level PR comment containing all review items
    for that file as clearly separated sections.
    """
    try:
        github_service = GitHubService(token=state.github_token or None)
        full_repo = f"{state.owner}/{state.repo_name}"
        pr_number = int(state.pr_id)

        posted = 0
        for raw in state.file_reviews:
            try:
                review = FileReviewOutput.model_validate_json(raw)
            except Exception:
                # Unparseable entry — post as-is
                github_service.post_pr_comment(full_repo, pr_number, raw)
                posted += 1
                continue

            body = review.to_markdown()
            github_service.post_pr_comment(full_repo, pr_number, body)
            posted += 1

        logger.info(
            "Posted %d file review comments for %s#%s",
            posted,
            full_repo,
            state.pr_id,
        )
        return {}
    except Exception as exc:
        logger.error(
            "Review post failed for %s#%s: %s",
            state.owner,
            state.repo_name,
            state.pr_id,
            exc,
        )
        return {"error": str(exc)}
