import logging

from agents.review import FileReviewOutput, ReviewItem, run_review
from state.models import SingleFileState

logger = logging.getLogger(__name__)


def review_node(state: SingleFileState) -> dict:
    """LangGraph node: review a single file diff and return structured results."""
    try:
        result = run_review(
            filename=state.filename,
            diff=state.diff,
            system_prompt=state.system_prompt,
            dependency_context=state.dependency_context,
            pr_title=state.pr_title,
            pr_body=state.pr_body,
        )
        return {"file_reviews": [result.model_dump_json()]}
    except Exception as exc:
        logger.error("Review node failed for %s: %s", state.filename, exc)
        error_review = FileReviewOutput(
            filename=state.filename,
            reviews=[
                ReviewItem(
                    title="Review node error",
                    detail=str(exc),
                    existing_code_to_replace="",
                    suggestion_for_change="Re-run the review.",
                    exact_code_replacement="",
                    critical_rate="Mid",
                )
            ],
        )
        return {"file_reviews": [error_review.model_dump_json()]}
