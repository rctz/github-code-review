import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from agents.dependency import run_dependency
from agents.persona import run_persona
from agents.review import FileReviewOutput, ReviewItem, _parse_response, run_review


class TestPersonaAgent:
    @patch("agents.persona.GitHubService")
    @patch("agents.persona.LLMFactory")
    def test_run_persona_returns_string(self, mock_factory: MagicMock, mock_github_cls: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_llm.chat.return_value = "You are a reviewer for Python projects."
        mock_factory.create.return_value = mock_llm
        mock_github_cls.return_value.fetch_file_content.return_value = "# My Project\nA FastAPI app."

        result = run_persona("my-repo", "my-org", "gh_token")
        assert isinstance(result, str)
        assert len(result) > 0
        mock_factory.create.assert_called_once()

    @patch("agents.persona.GitHubService")
    @patch("agents.persona.LLMFactory")
    def test_run_persona_uses_repo_name(self, mock_factory: MagicMock, mock_github_cls: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_llm.chat.return_value = "System prompt"
        mock_factory.create.return_value = mock_llm
        mock_github_cls.return_value.fetch_file_content.return_value = "# My Repo"

        run_persona("my-repo", "my-org", "gh_token")
        call_args = mock_llm.chat.call_args[0][0]
        assert "my-repo" in call_args

    @patch("agents.persona.GitHubService")
    @patch("agents.persona.LLMFactory")
    def test_run_persona_includes_project_context_in_prompt(self, mock_factory: MagicMock, mock_github_cls: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_llm.chat.return_value = "ROS2-focused reviewer"
        mock_factory.create.return_value = mock_llm
        mock_github_cls.return_value.fetch_file_content.return_value = "# ROS2 Navigation Stack\nUses rclpy and nav2."

        run_persona("nav_stack", "robotics-org", "gh_token")
        call_args = mock_llm.chat.call_args[0][0]
        assert "ROS2 Navigation Stack" in call_args

    @patch("agents.persona.GitHubService")
    @patch("agents.persona.LLMFactory")
    def test_run_persona_fallback_when_no_context(self, mock_factory: MagicMock, mock_github_cls: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_llm.chat.return_value = "Generic reviewer"
        mock_factory.create.return_value = mock_llm
        mock_github_cls.return_value.fetch_file_content.return_value = "[Error fetching README.md: HTTP 404]"

        result = run_persona("my-repo", "my-org", "gh_token")
        assert isinstance(result, str)
        call_args = mock_llm.chat.call_args[0][0]
        assert "No README" in call_args


class TestDependencyAgent:
    def _make_mock_service(self, **overrides: str) -> MagicMock:
        service = MagicMock()
        service.fetch_file_content.return_value = overrides.get(
            "content", "def helper(): pass"
        )
        return service

    def test_no_resolver_for_unknown_ext(self) -> None:
        service = self._make_mock_service()
        result = run_dependency(
            filename="README.md",
            diff="+some change",
            repo_name="owner/repo",
            head_sha="abc123",
            github_service=service,
        )
        assert result == "No external dependencies detected in this diff."
        service.fetch_file_content.assert_not_called()

    def test_python_imports_fetch_content(self) -> None:
        service = self._make_mock_service()
        result = run_dependency(
            filename="src/app.py",
            diff="+from utils import helper",
            repo_name="owner/repo",
            head_sha="abc123",
            github_service=service,
        )
        assert "###" in result
        assert "utils" in result
        service.fetch_file_content.assert_called()

    def test_fetch_error_skipped(self) -> None:
        service = MagicMock()
        service.fetch_file_content.return_value = "[Error fetching utils.py: HTTP 404]"
        result = run_dependency(
            filename="src/app.py",
            diff="+from utils import helper",
            repo_name="owner/repo",
            head_sha="abc123",
            github_service=service,
        )
        assert result == "No external dependencies detected in this diff."

    def test_cpp_resolver_fetches_headers(self) -> None:
        service = self._make_mock_service()
        result = run_dependency(
            filename="src/node.cpp",
            diff='+#include "node.hpp"',
            repo_name="org/my_pkg",
            head_sha="abc123",
            github_service=service,
        )
        assert "###" in result
        service.fetch_file_content.assert_called()

    def test_no_imports_returns_no_deps_message(self) -> None:
        service = self._make_mock_service()
        result = run_dependency(
            filename="app.py",
            diff="+x = 1",
            repo_name="owner/repo",
            head_sha="abc123",
            github_service=service,
        )
        assert result == "No external dependencies detected in this diff."

    def test_calls_fetch_with_correct_args(self) -> None:
        service = self._make_mock_service()
        run_dependency(
            filename="src/app.py",
            diff="+from utils import helper",
            repo_name="owner/repo",
            head_sha="deadbeef",
            github_service=service,
        )
        call_args = service.fetch_file_content.call_args_list[0]
        assert call_args[0][0] == "owner/repo"
        assert call_args[1]["ref"] == "deadbeef"


class TestReviewAgent:
    def test_parse_valid_json(self, sample_review_json: str) -> None:
        result = _parse_response(sample_review_json, "src/test.py")
        assert isinstance(result, FileReviewOutput)
        assert result.filename == "src/test.py"
        assert len(result.reviews) == 1
        assert result.reviews[0].critical_rate == "High"

    def test_parse_json_with_markdown_fences(self, sample_review_json: str) -> None:
        wrapped = f"```json\n{sample_review_json}\n```"
        result = _parse_response(wrapped, "src/test.py")
        assert isinstance(result, FileReviewOutput)
        assert result.filename == "src/test.py"

    def test_parse_json_missing_filename(self) -> None:

        json_str = json.dumps(
            {
                "reviews": [
                    {
                        "title": "t",
                        "detail": "d",
                        "existing_code_to_replace": "old",
                        "suggestion_for_change": "s",
                        "exact_code_replacement": "new",
                        "critical_rate": "Mid",
                    }
                ]
            }
        )
        result = _parse_response(json_str, "fallback.py")
        assert result.filename == "fallback.py"

    def test_review_item_title_validation_rejects_long(self) -> None:
        long_title = (
            "This is an intentionally very long title that will clearly exceed the fifteen word validation limit"
        )
        assert len(long_title.split()) > 15, "Test title must be > 15 words"

        with pytest.raises(ValidationError, match="title must not exceed 15 words"):
            ReviewItem(
                title=long_title,
                detail="detail",
                existing_code_to_replace="old",
                suggestion_for_change="suggestion",
                exact_code_replacement="new",
                critical_rate="High",
            )

    def test_review_item_title_validation_accepts_short(self) -> None:
        item = ReviewItem(
            title="Short title",
            detail="detail",
            existing_code_to_replace="old code",
            suggestion_for_change="suggestion",
            exact_code_replacement="new code",
            critical_rate="Mid",
        )
        assert item.title == "Short title"

    @patch("agents.review.LLMFactory")
    def test_run_review_returns_file_review_output(self, mock_factory: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_llm.chat.return_value = (
            '{"filename": "src/test.py", "reviews": '
            '[{"title": "Issue", "detail": "desc", '
            '"existing_code_to_replace": "old", '
            '"suggestion_for_change": "fix", '
            '"exact_code_replacement": "new", '
            '"critical_rate": "Mid"}]}'
        )
        mock_factory.create.return_value = mock_llm

        result = run_review(
            filename="src/test.py",
            diff="+def foo():\n+    pass",
            system_prompt="You are a reviewer.",
            dependency_context="No dependencies.",
        )
        assert isinstance(result, FileReviewOutput)
        assert result.filename == "src/test.py"

    @patch("agents.review.LLMFactory")
    def test_run_review_handles_invalid_json(self, mock_factory: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_llm.chat.return_value = "NOT VALID JSON"
        mock_factory.create.return_value = mock_llm

        result = run_review(
            filename="src/test.py",
            diff="+x = 1",
            system_prompt="reviewer",
            dependency_context="",
        )
        assert isinstance(result, FileReviewOutput)
        assert "parse error" in result.reviews[0].title.lower()


class TestFileReviewOutput:
    def test_to_markdown(self, sample_file_review_output: FileReviewOutput) -> None:
        md = sample_file_review_output.to_markdown()
        assert "src/test.py" in md
        assert "Missing type hints" in md
        assert "🟡" in md  # Mid severity emoji

    def test_to_markdown_high_severity(self) -> None:
        output = FileReviewOutput(
            filename="auth.py",
            reviews=[
                ReviewItem(
                    title="SQL injection",
                    detail="Unsafe query",
                    existing_code_to_replace="f'SELECT * FROM users WHERE name={name}'",
                    suggestion_for_change="Use parameterized queries",
                    exact_code_replacement="'SELECT * FROM users WHERE name=?', [name]",
                    critical_rate="High",
                )
            ],
        )
        md = output.to_markdown()
        assert "🟠" in md  # High severity emoji
        assert "auth.py" in md
