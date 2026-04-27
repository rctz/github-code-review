import logging

from agents.synthesis import run_synthesis
from state.models import PRReviewState

logger = logging.getLogger(__name__)


def synthesis_node(state: PRReviewState) -> dict:
    """LangGraph node: cross-file review after all per-file reviews complete."""
    try:
        result = run_synthesis(
            pr_files=state.pr_files,
            file_reviews=state.file_reviews,
            pr_title=state.pr_title,
            pr_body=state.pr_body,
            system_prompt=state.system_prompt,
        )
        md = result.to_markdown()
        return {"synthesis_reviews": [md] if md else []}
    except Exception as exc:
        logger.error("Synthesis node failed: %s", exc)
        return {"synthesis_reviews": []}
