from unittest.mock import MagicMock, patch

import pytest

from agents.dependency import _extract_imported_files, run_dependency
from agents.persona import run_persona
from agents.review import FileReviewOutput, ReviewItem, _parse_response, run_review


class TestPersonaAgent:
    @patch("agents.persona.LLMFactory")
    def test_run_persona_returns_string(self, mock_factory: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_llm.chat.return_value = "You are a reviewer for Python projects."
        mock_factory.create.return_value = mock_llm

        result = run_persona("owner/repo")
        assert isinstance(result, str)
        assert len(result) > 0
        mock_factory.create.assert_called_once()

    @patch("agents.persona.LLMFactory")
    def test_run_persona_uses_repo_name(self, mock_factory: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_llm.chat.return_value = "System prompt"
        mock_factory.create.return_value = mock_llm

        run_persona("my-org/my-repo")
        call_args = mock_llm.chat.call_args[0][0]
        assert "my-org/my-repo" in call_args


class TestDependencyAgent:
    def test_extract_python_imports(self) -> None:
        diff = "+from utils import helper\n+import os\n-some line"
        result = _extract_imported_files(diff)
        assert "utils" in result or "os" in result

    def test_extract_js_imports(self) -> None:
        diff = '+require("express")\n+import "lodash"'
        result = _extract_imported_files(diff)
        assert len(result) > 0

    def test_no_imports_returns_empty(self) -> None:
        diff = "+x = 1\n+y = 2"
        result = _extract_imported_files(diff)
        assert result == []

    def test_run_dependency_no_imports(self) -> None:
        result = run_dependency("+x = 1")
        assert result == "No external dependencies detected in this diff."

    def test_run_dependency_with_imports(self) -> None:
        diff = "+import os\n+import sys"
        result = run_dependency(diff)
        assert "###" in result


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
        json_str = '{"reviews": [{"title": "t", "detail": "d", "suggestion_for_change": "s", "critical_rate": "Low"}]}'
        result = _parse_response(json_str, "fallback.py")
        assert result.filename == "fallback.py"

    def test_review_item_title_validation_rejects_long(self) -> None:
        from pydantic import ValidationError

        long_title = (
            "This is an intentionally very long title that will clearly exceed the fifteen word validation limit"
        )
        assert len(long_title.split()) > 15, "Test title must be > 15 words"

        with pytest.raises(ValidationError, match="title must not exceed 15 words"):
            ReviewItem(
                title=long_title,
                detail="detail",
                suggestion_for_change="suggestion",
                critical_rate="High",
            )

    def test_review_item_title_validation_accepts_short(self) -> None:
        item = ReviewItem(
            title="Short title",
            detail="detail",
            suggestion_for_change="suggestion",
            critical_rate="Mid",
        )
        assert item.title == "Short title"

    @patch("agents.review.LLMFactory")
    def test_run_review_returns_file_review_output(self, mock_factory: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_llm.chat.return_value = (
            '{"filename": "src/test.py", "reviews": '
            '[{"title": "Issue", "detail": "desc", '
            '"suggestion_for_change": "fix", "critical_rate": "Low"}]}'
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
        assert "🟢" in md  # Low severity emoji

    def test_to_markdown_high_severity(self) -> None:
        output = FileReviewOutput(
            filename="auth.py",
            reviews=[
                ReviewItem(
                    title="SQL injection",
                    detail="Unsafe query",
                    suggestion_for_change="Use parameterized queries",
                    critical_rate="High",
                )
            ],
        )
        md = output.to_markdown()
        assert "🔴" in md
        assert "auth.py" in md
