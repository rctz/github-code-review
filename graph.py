from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from nodes.aggregate_node import aggregate_node
from nodes.dependency_node import dependency_node
from nodes.persona_node import persona_node
from nodes.review_node import review_node
from state import PRReviewState, SingleFileOutput, SingleFileState


# ── Subgraph: single-file review pipeline (dependency → review) ────────────


def _build_file_review_subgraph() -> CompiledStateGraph:
    """Compile a subgraph that runs dependency analysis → review for ONE file."""
    sub = StateGraph(SingleFileState, output=SingleFileOutput)
    sub.add_node("dependency_node", dependency_node)
    sub.add_node("review_node", review_node)
    sub.add_edge(START, "dependency_node")
    sub.add_edge("dependency_node", "review_node")
    sub.add_edge("review_node", END)
    return sub.compile()


# ── Fan-out: map each file to a parallel subgraph invocation ───────────────


def _map_files_to_review(state: PRReviewState) -> list[Send]:
    seen: set[str] = set()
    sends: list[Send] = []
    for file in state["pr_files"]:
        filename = file["filename"]
        if filename in seen:
            continue
        seen.add(filename)
        sends.append(
            Send(
                "review_single_file",
                {
                    "pr_id": state["pr_id"],
                    "repo_name": state["repo_name"],
                    "filename": filename,
                    "diff": file["diff"],
                    "system_prompt": state["system_prompt"],
                    "dependency_context": "",
                    "file_reviews": [],
                },
            )
        )
    return sends


# ── Build the graph ──────────────────────────────────────────────────────────


def build_graph() -> StateGraph:
    graph = StateGraph(PRReviewState)

    graph.add_node("persona_node", persona_node)
    graph.add_node("review_single_file", _build_file_review_subgraph())
    graph.add_node("aggregate_node", aggregate_node)

    graph.add_edge(START, "persona_node")
    graph.add_conditional_edges(
        "persona_node", _map_files_to_review, ["review_single_file"]
    )
    graph.add_edge("review_single_file", "aggregate_node")
    graph.add_edge("aggregate_node", END)

    return graph


app = build_graph().compile()
