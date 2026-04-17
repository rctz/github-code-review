import logging

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from nodes.aggregate_node import aggregate_node
from nodes.dependency_node import dependency_node
from nodes.fetch_sha_node import fetch_sha_node
from nodes.persona_node import persona_node
from nodes.post_review_node import post_review_node
from nodes.review_node import review_node
from state.models import PRReviewState, SingleFileOutput, SingleFileState

logger = logging.getLogger(__name__)


def _build_file_review_subgraph() -> CompiledStateGraph:
    """Compile a subgraph that runs dependency analysis -> review for ONE file."""
    sub = StateGraph(SingleFileState, output_schema=SingleFileOutput)
    sub.add_node("dependency_node", dependency_node)
    sub.add_node("review_node", review_node)
    sub.add_edge(START, "dependency_node")
    sub.add_edge("dependency_node", "review_node")
    sub.add_edge("review_node", END)
    return sub.compile()


def _map_files_to_review(state: PRReviewState) -> list[Send]:
    """Fan-out: map each file to a parallel subgraph invocation."""
    seen: set[str] = set()
    sends: list[Send] = []
    for file in state.pr_files:
        filename = file["filename"]
        if filename in seen:
            continue
        diff = file.get("diff") or ""
        if not diff:
            logger.info("Skipping file with no diff: %s", filename)
            continue
        seen.add(filename)
        file = SingleFileState(
            pr_id=state.pr_id,
            owner=state.owner,
            repo_name=state.repo_name,
            head_sha=state.head_sha,
            github_token=state.github_token,
            filename=filename,
            diff=diff,
            system_prompt=state.system_prompt,
        )
        sends.append(
            Send(
                "review_single_file",
                file,
            )
        )
    logger.info("Fan-out: %d files to review", len(sends))
    return sends


def build_graph() -> StateGraph:
    """Build the PR review StateGraph (uncompiled)."""
    graph = StateGraph(PRReviewState)

    graph.add_node("persona_node", persona_node)
    graph.add_node("fetch_sha_node", fetch_sha_node)
    graph.add_node("review_single_file", _build_file_review_subgraph())
    graph.add_node("aggregate_node", aggregate_node)
    graph.add_node("post_review_node", post_review_node)

    graph.add_edge(START, "persona_node")
    graph.add_edge("persona_node", "fetch_sha_node")
    graph.add_conditional_edges("fetch_sha_node", _map_files_to_review, ["review_single_file"])
    graph.add_edge("review_single_file", "aggregate_node")
    graph.add_edge("aggregate_node", "post_review_node")
    graph.add_edge("post_review_node", END)

    return graph


def build_compiled_graph() -> CompiledStateGraph:
    """Build and compile the PR review graph."""
    return build_graph().compile()
