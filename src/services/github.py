import base64
import logging

import requests
from github import Auth, Github
from tenacity import before_sleep_log, retry, stop_after_attempt, wait_exponential

from config.settings import settings

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"


class GitHubService:
    """Abstracts all GitHub API interactions behind a clean interface."""

    def __init__(self, token: str | None = None):
        self._token = token or settings.github_token
        if not self._token:
            raise ValueError("GITHUB_TOKEN is not configured")
        self._client = Github(auth=Auth.Token(self._token))

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def fetch_diff(self, repo_name: str, owner: str, pr_id: int) -> list[dict]:
        """Fetch file diffs for a pull request.

        Args:
            repo_name: Repository name (without owner).
            owner: Repository owner.
            pr_id: Pull request number.

        Returns:
            List of dicts with "filename", "diff", and "raw" keys.
        """
        repo = self._client.get_repo(f"{owner}/{repo_name}")
        pull = repo.get_pull(pr_id)
        diffs = []
        for file in pull.get_files():
            diffs.append(
                {
                    "filename": file.filename,
                    "diff": file.patch,
                    "raw": file.raw_data,
                }
            )
        logger.info("Fetched %d file diffs for %s/%s#%d", len(diffs), owner, repo_name, pr_id)
        return diffs

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def fetch_file_content(self, repo_name: str, file_path: str, ref: str = "main") -> str:
        """Fetch the raw content of a file from GitHub.

        Args:
            repo_name: Full repo name (e.g., "owner/repo").
            file_path: Path inside the repo.
            ref: Branch or commit SHA.

        Returns:
            Raw file content as string, or an error message.
        """
        url = f"{_GITHUB_API}/repos/{repo_name}/contents/{file_path}"
        resp = requests.get(url, headers=self._headers(), params={"ref": ref}, timeout=10)
        if resp.status_code != 200:
            return f"[Error fetching {file_path}: HTTP {resp.status_code}]"

        data = resp.json()
        if data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8")
        return data.get("content", "")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def create_pr_review(self, repo_name: str, pr_number: int, body: str, event: str = "COMMENT") -> bool:
        """Create a PR review comment using the GitHub Reviews API.

        Args:
            repo_name: Full repo name (e.g., "owner/repo").
            pr_number: Pull request number.
            body: The review body (markdown).
            event: Review event type — "COMMENT", "APPROVE", or "REQUEST_CHANGES".

        Returns:
            True if successful.
        """
        url = f"{_GITHUB_API}/repos/{repo_name}/pulls/{pr_number}/reviews"
        payload = {"body": body, "event": event}
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=10)
        success = resp.status_code == 201
        if success:
            logger.info("Created PR review on %s#%d", repo_name, pr_number)
        else:
            logger.error("Failed to create PR review on %s#%d: HTTP %d", repo_name, pr_number, resp.status_code)
        return success

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def post_pr_comment(self, repo_name: str, pr_number: int, body: str) -> bool:
        """Post a review comment on a GitHub PR.

        Returns:
            True if successful.
        """
        url = f"{_GITHUB_API}/repos/{repo_name}/issues/{pr_number}/comments"
        resp = requests.post(url, headers=self._headers(), json={"body": body}, timeout=10)
        success = resp.status_code == 201
        if success:
            logger.info("Posted comment on %s#%d", repo_name, pr_number)
        else:
            logger.error("Failed to post comment on %s#%d: HTTP %d", repo_name, pr_number, resp.status_code)
        return success
