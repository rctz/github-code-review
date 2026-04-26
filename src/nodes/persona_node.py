import logging

from agents.persona import run_persona
from state.models import PRReviewState

logger = logging.getLogger(__name__)


def persona_node(state: PRReviewState) -> dict:
    """LangGraph node: generate a reviewer system prompt from the project context."""
    try:
        system_prompt = run_persona(state.repo_name, state.owner, state.github_token)
        logger.info("Generated system prompt for %s/%s promp is %s", state.owner, state.repo_name, system_prompt)
        return {"system_prompt": system_prompt}
    except Exception as exc:
        logger.error("Persona node failed: %s", exc)
        return {"error": f"Persona generation failed: {exc}"}
