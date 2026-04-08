from unittest.mock import MagicMock

import pytest

from agents.review import FileReviewOutput, ReviewItem
from providers.base import LLMProvider


@pytest.fixture
def mock_llm_provider() -> MagicMock:
    """Create a mock LLM provider."""
    provider = MagicMock(spec=LLMProvider)
    provider.chat.return_value = "Mock LLM response"
    return provider


@pytest.fixture
def mock_github_service() -> MagicMock:
    """Create a mock GitHub service."""
    service = MagicMock()
    service.fetch_diff.return_value = [
        {"filename": "src/test.py", "diff": "+def foo():\n+    pass", "raw": {}},
        {"filename": "src/bar.py", "diff": "+import os\n+def bar():\n+    pass", "raw": {}},
    ]
    service.post_pr_comment.return_value = True
    return service


@pytest.fixture
def sample_file_review_output() -> FileReviewOutput:
    """Create a sample FileReviewOutput."""
    return FileReviewOutput(
        filename="src/test.py",
        reviews=[
            ReviewItem(
                title="Missing type hints",
                detail="Function foo lacks type annotations.",
                suggestion_for_change="Add type hints: def foo() -> None:",
                critical_rate="Low",
            )
        ],
    )


@pytest.fixture
def sample_review_json() -> str:
    """Return a valid JSON string for FileReviewOutput."""
    return """{
    "filename": "src/test.py",
    "reviews": [
        {
            "title": "SQL injection risk",
            "detail": "Query uses string formatting with user input.",
            "suggestion_for_change": "Use parameterized queries.",
            "critical_rate": "High"
        }
    ]
}"""
