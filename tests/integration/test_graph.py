from unittest.mock import MagicMock, patch

from graph.builder import build_compiled_graph
from state.models import PRReviewState


def _make_initial_state() -> dict:
    return PRReviewState(
        pr_id="42",
        repo_name="owner/repo",
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

        mock_output = MagicMock()
        mock_output.to_markdown.return_value = "### 📄 `test.py`\nLGTM"
        mock_review.return_value = mock_output

        graph = build_compiled_graph()
        result = graph.invoke(_make_initial_state())

        assert result["final_comment"]
        assert "owner/repo" in result["final_comment"]
        assert "#42" in result["final_comment"]
        assert len(result["file_reviews"]) == 2
        mock_persona.assert_called_once_with("owner/repo")
        assert mock_review.call_count == 2

    @patch("nodes.review_node.run_review")
    @patch("nodes.persona_node.run_persona")
    def test_graph_deduplicates_files(self, mock_persona: MagicMock, mock_review: MagicMock) -> None:
        mock_persona.return_value = "Reviewer persona."

        mock_output = MagicMock()
        mock_output.to_markdown.return_value = "Review"
        mock_review.return_value = mock_output

        state = PRReviewState(
            pr_id="1",
            repo_name="owner/repo",
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
        result = graph.invoke(_make_initial_state())

        # Graph should complete despite review failures (error handled in node)
        assert result["final_comment"]
        assert "Error" in result["final_comment"]
