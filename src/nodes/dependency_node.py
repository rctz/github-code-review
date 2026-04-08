import logging

from agents.dependency import run_dependency
from state.models import SingleFileState

logger = logging.getLogger(__name__)


def dependency_node(state: SingleFileState) -> dict:
    """LangGraph node: extract dependency context from a file diff."""
    if state.diff:
        context = run_dependency(state.diff)
        return {"dependency_context": context}
    return {"dependency_context": ""}
