from agents.review import run_review
from state import SingleFileState


def review_node(state: SingleFileState) -> dict:
    """LangGraph node: review a single file diff and return structured results."""
    result = run_review(
        filename=state["filename"],
        diff=state["diff"],
        system_prompt=state["system_prompt"],
        dependency_context=state.get("dependency_context", ""),
    )
    return {"file_reviews": [result.model_dump_json(indent=2)]}
