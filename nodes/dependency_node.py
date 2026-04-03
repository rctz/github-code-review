from agents.dependency import run_dependency
from state import SingleFileState


def dependency_node(state: SingleFileState) -> dict:
    """LangGraph node: extract dependency context from a file diff."""
    dependency_context = run_dependency(state["diff"])
    return {"dependency_context": dependency_context}
