from unittest.mock import MagicMock, patch

from nodes.aggregate_node import aggregate_node
from nodes.dependency_node import dependency_node
from nodes.error_node import error_node
from nodes.persona_node import persona_node
from nodes.review_node import review_node
from state.models import PRReviewState, SingleFileState


class TestPersonaNode:
    @patch("nodes.persona_node.run_persona")
    def test_persona_node_success(self, mock_run_persona: MagicMock) -> None:
        mock_run_persona.return_value = "You are a Python reviewer."
        state = PRReviewState(
            pr_id="1", repo_name="owner/repo", pr_files=[{"filename": "a.py", "diff": "+x", "raw": {}}]
        )
        result = persona_node(state)
        assert result["system_prompt"] == "You are a Python reviewer."
        assert "error" not in result

    @patch("nodes.persona_node.run_persona")
    def test_persona_node_handles_error(self, mock_run_persona: MagicMock) -> None:
        mock_run_persona.side_effect = RuntimeError("LLM unavailable")
        state = PRReviewState(pr_id="1", repo_name="owner/repo", pr_files=[])
        result = persona_node(state)
        assert "error" in result
        assert "Persona generation failed" in result["error"]


class TestDependencyNode:
    @patch("nodes.dependency_node.run_dependency")
    def test_dependency_node_with_diff(self, mock_run_dep: MagicMock) -> None:
        mock_run_dep.return_value = "### utils.py\n```\n```"
        state = SingleFileState(
            pr_id="1",
            repo_name="owner/repo",
            filename="test.py",
            diff="+import utils",
        )
        result = dependency_node(state)
        assert result["dependency_context"] == "### utils.py\n```\n```"

    def test_dependency_node_empty_diff(self) -> None:
        state = SingleFileState(pr_id="1", repo_name="owner/repo", filename="test.py", diff="")
        result = dependency_node(state)
        assert result["dependency_context"] == ""


class TestReviewNode:
    @patch("nodes.review_node.run_review")
    def test_review_node_success(self, mock_run_review: MagicMock) -> None:
        mock_output = MagicMock()
        mock_output.to_markdown.return_value = "### 📄 `test.py`\nReview content"
        mock_run_review.return_value = mock_output

        state = SingleFileState(
            pr_id="1",
            repo_name="owner/repo",
            filename="test.py",
            diff="+x = 1",
            system_prompt="You are a reviewer.",
            dependency_context="",
        )
        result = review_node(state)
        assert len(result["file_reviews"]) == 1
        assert "test.py" in result["file_reviews"][0]

    @patch("nodes.review_node.run_review")
    def test_review_node_handles_error(self, mock_run_review: MagicMock) -> None:
        mock_run_review.side_effect = RuntimeError("LLM error")
        state = SingleFileState(
            pr_id="1",
            repo_name="owner/repo",
            filename="broken.py",
            diff="+x = 1",
            system_prompt="reviewer",
            dependency_context="",
        )
        result = review_node(state)
        assert len(result["file_reviews"]) == 1
        assert "Error" in result["file_reviews"][0]


class TestAggregateNode:
    def test_aggregate_node_combines_reviews(self) -> None:
        state = PRReviewState(
            pr_id="42",
            repo_name="owner/repo",
            pr_files=[],
            file_reviews=["### File 1 review", "### File 2 review"],
        )
        result = aggregate_node(state)
        assert "File 1 review" in result["final_comment"]
        assert "File 2 review" in result["final_comment"]
        assert "owner/repo" in result["final_comment"]
        assert "#42" in result["final_comment"]

    def test_aggregate_node_empty_reviews(self) -> None:
        state = PRReviewState(pr_id="1", repo_name="owner/repo", pr_files=[])
        result = aggregate_node(state)
        assert "PR Review" in result["final_comment"]


class TestErrorNode:
    def test_error_node_with_message(self) -> None:
        state = PRReviewState(
            pr_id="1",
            repo_name="owner/repo",
            pr_files=[],
            error="Something went wrong",
        )
        result = error_node(state)
        assert "PR Review Failed" in result["final_comment"]
        assert "Something went wrong" in result["final_comment"]
        assert result["file_reviews"] == []

    def test_error_node_without_message(self) -> None:
        state = PRReviewState(pr_id="1", repo_name="owner/repo", pr_files=[])
        result = error_node(state)
        assert "Unknown error" in result["final_comment"]
