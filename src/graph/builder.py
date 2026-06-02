import logging
from pathlib import Path

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from nodes.aggregate_node import aggregate_node
from nodes.context_node import context_node
from nodes.fetch_sha_node import fetch_sha_node
from nodes.fetch_tree_node import fetch_tree_node
from nodes.persona_node import persona_node
from nodes.post_review_node import post_review_node
from nodes.review_node import review_node
from nodes.synthesis_node import synthesis_node
from state.models import PRReviewState, SingleFileOutput, SingleFileState

logger = logging.getLogger(__name__)

_DOC_EXTENSIONS = {".md", ".rst", ".txt", ".adoc"}
_COMMENT_PREFIXES = ("#", "//", "*", "/*", "*/", "<!--", "-->")


def _is_reviewable(filename: str, diff: str) -> bool:
    """Return False for files that carry no reviewable code change."""
    if Path(filename).suffix.lower() in _DOC_EXTENSIONS:
        return False
    added_lines = [
        line[1:].strip() for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")
    ]
    non_trivial = [line for line in added_lines if line and not any(line.startswith(p) for p in _COMMENT_PREFIXES)]
    return bool(non_trivial)


def _build_file_review_subgraph() -> CompiledStateGraph:
    """Compile a subgraph that runs context selection -> review for ONE file."""
    sub = StateGraph(SingleFileState, output_schema=SingleFileOutput)
    sub.add_node("context_node", context_node)
    sub.add_node("review_node", review_node)
    sub.add_edge(START, "context_node")
    sub.add_edge("context_node", "review_node")
    sub.add_edge("review_node", END)
    return sub.compile()


def _map_files_to_review(state: PRReviewState) -> list[Send]:
    """Fan-out: map each reviewable file to a parallel subgraph invocation."""
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
        if not _is_reviewable(filename, diff):
            logger.info("Skipping non-reviewable file: %s", filename)
            continue
        seen.add(filename)
        sends.append(
            Send(
                "review_single_file",
                SingleFileState(
                    pr_id=state.pr_id,
                    owner=state.owner,
                    repo_name=state.repo_name,
                    head_sha=state.head_sha,
                    github_token=state.github_token,
                    pr_title=state.pr_title,
                    pr_body=state.pr_body,
                    filename=filename,
                    diff=diff,
                    system_prompt=state.system_prompt,
                    repo_tree=state.repo_tree,
                ),
            )
        )
    logger.info("Fan-out: %d files to review", len(sends))
    return sends


def build_graph() -> StateGraph:
    """Build the PR review StateGraph (uncompiled)."""
    graph = StateGraph(PRReviewState)

    graph.add_node("persona_node", persona_node)
    graph.add_node("fetch_sha_node", fetch_sha_node)
    graph.add_node("fetch_tree_node", fetch_tree_node)
    graph.add_node("review_single_file", _build_file_review_subgraph())
    graph.add_node("synthesis_node", synthesis_node)
    graph.add_node("aggregate_node", aggregate_node)
    graph.add_node("post_review_node", post_review_node)

    graph.add_edge(START, "persona_node")
    graph.add_edge("persona_node", "fetch_sha_node")
    graph.add_edge("fetch_sha_node", "fetch_tree_node")
    graph.add_conditional_edges("fetch_tree_node", _map_files_to_review, ["review_single_file"])
    graph.add_edge("review_single_file", "synthesis_node")
    graph.add_edge("synthesis_node", "aggregate_node")
    graph.add_edge("aggregate_node", "post_review_node")
    graph.add_edge("post_review_node", END)

    return graph


def build_compiled_graph() -> CompiledStateGraph:
    """Build and compile the PR review graph."""
    return build_graph().compile()
