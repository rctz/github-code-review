import json
from unittest.mock import MagicMock, patch

from agents.review import FileReviewOutput, ReviewItem
from nodes.aggregate_node import aggregate_node
from nodes.dependency_node import dependency_node
from nodes.error_node import error_node
from nodes.persona_node import persona_node
from nodes.review_node import review_node
from state.models import PRReviewState, SingleFileState


def _make_review_json(filename: str = "test.py", title: str = "Issue") -> str:
    """Helper to build a FileReviewOutput JSON string."""
    output = FileReviewOutput(
        filename=filename,
        reviews=[
            ReviewItem(
                title=title,
                detail="Some detail",
                existing_code_to_replace="old",
                suggestion_for_change="fix",
                exact_code_replacement="new",
                critical_rate="Mid",
            )
        ],
    )
    return output.model_dump_json()


def _make_single_file_state(**overrides: object) -> SingleFileState:
    defaults = {
        "pr_id": "1",
        "owner": "owner",
        "repo_name": "repo",
        "head_sha": "abc123",
        "github_token": "",
        "filename": "test.py",
        "diff": "+import utils",
        "system_prompt": "",
        "dependency_context": "",
    }
    defaults.update(overrides)
    return SingleFileState(**defaults)  # type: ignore[arg-type]


class TestPersonaNode:
    @patch("nodes.persona_node.run_persona")
    def test_persona_node_success(self, mock_run_persona: MagicMock) -> None:
        mock_run_persona.return_value = "You are a Python reviewer."
        state = PRReviewState(
            pr_id="1", owner="owner", repo_name="repo", pr_files=[{"filename": "a.py", "diff": "+x", "raw": {}}]
        )
        result = persona_node(state)
        assert result["system_prompt"] == "You are a Python reviewer."
        assert "error" not in result

    @patch("nodes.persona_node.run_persona")
    def test_persona_node_handles_error(self, mock_run_persona: MagicMock) -> None:
        mock_run_persona.side_effect = RuntimeError("LLM unavailable")
        state = PRReviewState(pr_id="1", owner="owner", repo_name="repo", pr_files=[])
        result = persona_node(state)
        assert "error" in result
        assert "Persona generation failed" in result["error"]


class TestDependencyNode:
    @patch("nodes.dependency_node.GitHubService")
    @patch("nodes.dependency_node.run_dependency")
    def test_dependency_node_with_diff(self, mock_run_dep: MagicMock, mock_gh_cls: MagicMock) -> None:
        mock_run_dep.return_value = "### utils.py\n```\ndef helper(): pass\n```"
        state = _make_single_file_state(diff="+import utils")
        result = dependency_node(state)
        assert result["dependency_context"] == "### utils.py\n```\ndef helper(): pass\n```"
        mock_run_dep.assert_called_once()

    def test_dependency_node_empty_diff(self) -> None:
        state = _make_single_file_state(diff="")
        result = dependency_node(state)
        assert result["dependency_context"] == ""

    @patch("nodes.dependency_node.GitHubService")
    @patch("nodes.dependency_node.run_dependency")
    def test_dependency_node_constructs_full_repo(self, mock_run_dep: MagicMock, mock_gh_cls: MagicMock) -> None:
        mock_run_dep.return_value = "context"
        state = _make_single_file_state(owner="my-org", repo_name="my-repo")
        dependency_node(state)
        call_kwargs = mock_run_dep.call_args
        assert call_kwargs[1]["repo_name"] == "my-org/my-repo" or call_kwargs[0][2] == "my-org/my-repo"

    @patch("nodes.dependency_node.GitHubService")
    @patch("nodes.dependency_node.run_dependency")
    def test_dependency_node_handles_exception(self, mock_run_dep: MagicMock, mock_gh_cls: MagicMock) -> None:
        mock_run_dep.side_effect = RuntimeError("API down")
        state = _make_single_file_state()
        result = dependency_node(state)
        assert result["dependency_context"] == ""

    @patch("nodes.dependency_node.GitHubService")
    @patch("nodes.dependency_node.run_dependency")
    def test_dependency_node_passes_head_sha(self, mock_run_dep: MagicMock, mock_gh_cls: MagicMock) -> None:
        mock_run_dep.return_value = "ctx"
        state = _make_single_file_state(head_sha="deadbeef")
        dependency_node(state)
        call_args = mock_run_dep.call_args
        assert call_args.kwargs.get("head_sha") == "deadbeef" or "deadbeef" in str(call_args)


class TestReviewNode:
    @patch("nodes.review_node.run_review")
    def test_review_node_stores_json(self, mock_run_review: MagicMock) -> None:
        mock_output = FileReviewOutput(
            filename="test.py",
            reviews=[
                ReviewItem(
                    title="Bug",
                    detail="desc",
                    existing_code_to_replace="old",
                    suggestion_for_change="fix",
                    exact_code_replacement="new",
                    critical_rate="High",
                )
            ],
        )
        mock_run_review.return_value = mock_output

        state = _make_single_file_state(diff="+x = 1")
        result = review_node(state)
        assert len(result["file_reviews"]) == 1
        parsed = json.loads(result["file_reviews"][0])
        assert parsed["filename"] == "test.py"
        assert len(parsed["reviews"]) == 1

    @patch("nodes.review_node.run_review")
    def test_review_node_handles_error(self, mock_run_review: MagicMock) -> None:
        mock_run_review.side_effect = RuntimeError("LLM error")
        state = _make_single_file_state(diff="+x = 1", filename="broken.py")
        result = review_node(state)
        assert len(result["file_reviews"]) == 1
        parsed = json.loads(result["file_reviews"][0])
        assert "error" in parsed["reviews"][0]["title"].lower()


class TestAggregateNode:
    def test_aggregate_node_parses_json_reviews(self) -> None:
        review_json = _make_review_json("src/auth.py", "SQL injection")
        state = PRReviewState(
            pr_id="42",
            owner="owner",
            repo_name="repo",
            pr_files=[],
            file_reviews=[review_json],
        )
        result = aggregate_node(state)
        assert "src/auth.py" in result["final_comment"]
        assert "SQL injection" in result["final_comment"]
        assert "repo" in result["final_comment"]
        assert "#42" in result["final_comment"]

    def test_aggregate_node_handles_raw_markdown_fallback(self) -> None:
        state = PRReviewState(
            pr_id="1",
            owner="owner",
            repo_name="repo",
            pr_files=[],
            file_reviews=["### Plain markdown fallback"],
        )
        result = aggregate_node(state)
        assert "Plain markdown fallback" in result["final_comment"]

    def test_aggregate_node_empty_reviews(self) -> None:
        state = PRReviewState(pr_id="1", owner="owner", repo_name="repo", pr_files=[])
        result = aggregate_node(state)
        assert "PR Review" in result["final_comment"]


class TestErrorNode:
    def test_error_node_with_message(self) -> None:
        state = PRReviewState(
            pr_id="1",
            owner="owner",
            repo_name="repo",
            pr_files=[],
            error="Something went wrong",
        )
        result = error_node(state)
        assert "PR Review Failed" in result["final_comment"]
        assert "Something went wrong" in result["final_comment"]
        assert result["file_reviews"] == []

    def test_error_node_without_message(self) -> None:
        state = PRReviewState(pr_id="1", owner="owner", repo_name="repo", pr_files=[])
        result = error_node(state)
        assert "Unknown error" in result["final_comment"]
