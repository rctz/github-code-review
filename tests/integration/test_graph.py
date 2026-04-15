from unittest.mock import MagicMock, patch

from agents.review import FileReviewOutput, ReviewItem
from graph.builder import build_compiled_graph
from state.models import PRReviewState


def _make_review_output(filename: str = "test.py") -> FileReviewOutput:
    return FileReviewOutput(
        filename=filename,
        reviews=[
            ReviewItem(
                title="LGTM",
                detail="No issues found.",
                existing_code_to_replace="",
                suggestion_for_change="No changes needed.",
                exact_code_replacement="",
                critical_rate="Mid",
            )
        ],
    )


def _make_initial_state() -> dict:
    return PRReviewState(
        pr_id="42",
        owner="owner",
        repo_name="repo",
        pr_files=[
            {"filename": "src/a.py", "diff": "+def a(): pass", "raw": {}},
            {"filename": "src/b.py", "diff": "+import os\n+def b(): pass", "raw": {}},
        ],
    ).model_dump()


class TestGraphIntegration:
    @patch("nodes.review_node.run_review")
    @patch("nodes.persona_node.run_persona")
    def test_full_graph_execution(self, mock_persona: MagicMock, mock_review: MagicMock) -> None:
        mock_persona.return_value = "You are a senior Python reviewer."
        mock_review.return_value = _make_review_output()

        graph = build_compiled_graph()
        result = graph.invoke(_make_initial_state())

        assert result["final_comment"]
        assert "repo" in result["final_comment"]
        assert "#42" in result["final_comment"]
        assert len(result["file_reviews"]) == 2
        mock_persona.assert_called_once_with("repo")
        assert mock_review.call_count == 2

    @patch("nodes.review_node.run_review")
    @patch("nodes.persona_node.run_persona")
    def test_graph_deduplicates_files(self, mock_persona: MagicMock, mock_review: MagicMock) -> None:
        mock_persona.return_value = "Reviewer persona."
        mock_review.return_value = _make_review_output("dup.py")

        state = PRReviewState(
            pr_id="1",
            owner="owner",
            repo_name="repo",
            pr_files=[
                {"filename": "dup.py", "diff": "+x", "raw": {}},
                {"filename": "dup.py", "diff": "+x", "raw": {}},
            ],
        ).model_dump()

        graph = build_compiled_graph()
        graph.invoke(state)

        # Should only review the file once despite duplicate filename
        assert mock_review.call_count == 1

    @patch("nodes.review_node.run_review")
    @patch("nodes.persona_node.run_persona")
    def test_graph_handles_review_failure(self, mock_persona: MagicMock, mock_review: MagicMock) -> None:
        mock_persona.return_value = "Reviewer."
        mock_review.side_effect = RuntimeError("LLM down")

        graph = build_compiled_graph()
        result = graph.invoke(_make_initial_state())  # already includes owner="owner"

        # Graph should complete despite review failures (error handled in node)
        assert result["final_comment"]
        assert "Review node error" in result["final_comment"]
