from unittest.mock import MagicMock, patch

import pytest

from services.github import GitHubService


class TestGitHubServiceInit:
    def test_init_with_token(self) -> None:
        svc = GitHubService(token="ghp_test123")
        assert svc._token == "ghp_test123"

    @patch("services.github.settings")
    def test_init_without_token_raises(self, mock_settings: MagicMock) -> None:
        mock_settings.github_token = ""
        with pytest.raises(ValueError, match="GITHUB_TOKEN"):
            GitHubService()  # type: ignore[name-defined]


class TestGitHubServiceFetchDiff:
    @patch("services.github.Github")
    def test_fetch_diff_returns_file_list(self, mock_github_cls: MagicMock) -> None:
        mock_file = MagicMock()
        mock_file.filename = "src/main.py"
        mock_file.patch = "+def main(): pass"
        mock_file.raw_data = {"sha": "abc123"}

        mock_pull = MagicMock()
        mock_pull.get_files.return_value = [mock_file]

        mock_repo = MagicMock()
        mock_repo.get_pull.return_value = mock_pull

        mock_github_cls.return_value.get_repo.return_value = mock_repo

        svc = GitHubService(token="ghp_test")
        result = svc.fetch_diff("my-repo", "owner", 42)

        assert len(result) == 1
        assert result[0]["filename"] == "src/main.py"
        assert result[0]["diff"] == "+def main(): pass"


class TestGitHubServicePostComment:
    @patch("services.github.requests")
    def test_post_pr_comment_success(self, mock_requests: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_requests.post.return_value = mock_resp

        svc = GitHubService(token="ghp_test")
        result = svc.post_pr_comment("owner/repo", 42, "Nice code!")
        assert result is True

    @patch("services.github.requests")
    def test_post_pr_comment_failure(self, mock_requests: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_requests.post.return_value = mock_resp

        svc = GitHubService(token="ghp_test")
        result = svc.post_pr_comment("owner/repo", 42, "Nice code!")
        assert result is False


class TestGitHubServiceFetchFileContent:
    @patch("services.github.requests")
    def test_fetch_file_content_success(self, mock_requests: MagicMock) -> None:
        import base64

        content = base64.b64encode(b"print('hello')").decode()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"encoding": "base64", "content": content}
        mock_requests.get.return_value = mock_resp

        svc = GitHubService(token="ghp_test")
        result = svc.fetch_file_content("owner/repo", "src/main.py")
        assert "print('hello')" in result

    @patch("services.github.requests")
    def test_fetch_file_content_not_found(self, mock_requests: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_requests.get.return_value = mock_resp

        svc = GitHubService(token="ghp_test")
        result = svc.fetch_file_content("owner/repo", "missing.py")
        assert "Error" in result
