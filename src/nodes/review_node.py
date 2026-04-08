import logging

from agents.review import run_review
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
        )
        return {"file_reviews": [result.to_markdown()]}
    except Exception as exc:
        logger.error("Review node failed for %s: %s", state.filename, exc)
        return {"file_reviews": [f"### Error reviewing `{state.filename}`\n\n{exc}"]}
