from agents.persona import run_persona
from state import PRReviewState


def persona_node(state: PRReviewState) -> dict:
    """LangGraph node: generate a reviewer system prompt from the repo name."""
    system_prompt = run_persona(state["repo_name"])
    return {"system_prompt": system_prompt}
