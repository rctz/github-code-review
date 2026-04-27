import base64
import logging

import requests
from github import Auth, Github
from tenacity import before_sleep_log, retry, stop_after_attempt, wait_exponential

from config.settings import settings

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"


def find_line_in_file(file_content: str, code_snippet: str) -> tuple[int, int] | None:
    """Find a code snippet in real file content and return its 1-based line range.

    Does an exact substring search against the file. Returns ``(start, end)``
    where both are 1-based line numbers, or ``None`` if not found.
    """
    snippet = code_snippet.strip()
    if not snippet:
        return None

    file_lines = file_content.splitlines()
    snippet_lines = snippet.splitlines()
    n = len(snippet_lines)

    for i in range(len(file_lines) - n + 1):
        chunk = "\n".join(file_lines[i : i + n])
        if chunk.strip() == snippet:
            return (i + 1, i + n)  # 1-based

    return None


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
    def create_review_with_comments(
        self,
        repo_name: str,
        pr_number: int,
        commit_id: str,
        comments: list[dict],
        body: str = "",
        event: str = "COMMENT",
    ) -> bool:
        """Create a PR review with multiple inline comments in a single API call.

        Uses ``POST /repos/{owner}/{repo}/pulls/{pr_number}/reviews`` with a
        ``comments`` array.  This avoids GitHub's secondary rate limit that
        fires when posting comments one-by-one.

        Each comment dict should contain:
            - ``path`` (str, required)
            - ``line`` (int, required)
            - ``body`` (str, required)
            - ``side`` (str, default "RIGHT")
            - ``start_line`` (int, optional — for multi-line)
            - ``start_side`` (str, optional — for multi-line)

        Returns:
            True if the review was created successfully.
        """
        url = f"{_GITHUB_API}/repos/{repo_name}/pulls/{pr_number}/reviews"
        payload = {
            "commit_id": commit_id,
            "body": body,
            "event": event,
            "comments": comments,
        }
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=15)
        success = resp.status_code == 200
        if success:
            logger.info(
                "Created review with %d inline comments on %s#%d",
                len(comments),
                repo_name,
                pr_number,
            )
        else:
            logger.error(
                "Failed to create review on %s#%d: HTTP %d %s",
                repo_name,
                pr_number,
                resp.status_code,
                resp.text[:300],
            )
        return success

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def fetch_pr_metadata(self, repo_name: str, owner: str, pr_id: int) -> tuple[str, str, str]:
        """Fetch the HEAD SHA, title, and body of a pull request in one call.

        Returns:
            (head_sha, title, body) — body may be empty string if the PR has no description.
        """
        repo = self._client.get_repo(f"{owner}/{repo_name}")
        pull = repo.get_pull(pr_id)
        sha = pull.head.sha
        title = pull.title or ""
        body = pull.body or ""
        logger.info("Fetched PR metadata for %s/%s#%d (sha=%s)", owner, repo_name, pr_id, sha[:7])
        return sha, title, body

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def fetch_pr_head_sha(self, repo_name: str, owner: str, pr_id: int) -> str:
        """Fetch the HEAD commit SHA of a pull request.

        Args:
            repo_name: Repository name (without owner).
            owner: Repository owner.
            pr_id: Pull request number.

        Returns:
            The SHA of the PR's head commit.
        """
        repo = self._client.get_repo(f"{owner}/{repo_name}")
        pull = repo.get_pull(pr_id)
        sha = pull.head.sha
        logger.info("Fetched HEAD SHA %s for %s/%s#%d", sha[:7], owner, repo_name, pr_id)
        return sha

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def create_inline_comment(
        self,
        repo_name: str,
        pr_number: int,
        commit_id: str,
        path: str,
        line: int,
        body: str,
        side: str = "RIGHT",
        start_line: int | None = None,
        start_side: str | None = None,
    ) -> bool:
        """Create an inline review comment on a specific line of a PR diff.

        Uses the GitHub "Create a review comment for a pull request" API:
        POST /repos/{owner}/{repo}/pulls/{pull_number}/comments

        Args:
            repo_name: Full repo name (e.g., "owner/repo").
            pr_number: Pull request number.
            commit_id: The SHA of the commit the comment applies to.
            path: The relative path to the file.
            line: The line number in the diff the comment applies to.
            body: The comment body (markdown).
            side: "LEFT" (deletions) or "RIGHT" (additions/unchanged).
            start_line: First line for multi-line comments.
            start_side: Starting side for multi-line comments.

        Returns:
            True if successful.
        """
        url = f"{_GITHUB_API}/repos/{repo_name}/pulls/{pr_number}/comments"
        payload: dict = {
            "body": body,
            "commit_id": commit_id,
            "path": path,
            "line": line,
            "side": side,
        }
        if start_line is not None:
            payload["start_line"] = start_line
        if start_side is not None:
            payload["start_side"] = start_side

        resp = requests.post(url, headers=self._headers(), json=payload, timeout=10)
        success = resp.status_code == 201
        if success:
            logger.info(
                "Created inline comment on %s#%d — %s:%d",
                repo_name,
                pr_number,
                path,
                line,
            )
        else:
            logger.error(
                "Failed to create inline comment on %s#%d — %s:%d: HTTP %d %s",
                repo_name,
                pr_number,
                path,
                line,
                resp.status_code,
                resp.text[:200],
            )
        return success

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def fetch_repo_tree(self, repo_name: str, tree_sha: str) -> list[str]:
        """Fetch all file paths in the repo at tree_sha via the GitHub Trees API.

        Uses ``GET /repos/{owner}/{repo}/git/trees/{tree_sha}?recursive=1``.
        Returns a flat list of blob paths (directories excluded).
        Returns an empty list on error. Logs a warning when GitHub truncates
        the response (very large repos).
        """
        url = f"{_GITHUB_API}/repos/{repo_name}/git/trees/{tree_sha}"
        resp = requests.get(
            url, headers=self._headers(), params={"recursive": "1"}, timeout=15
        )
        if resp.status_code != 200:
            logger.warning(
                "fetch_repo_tree failed for %s@%s: HTTP %d",
                repo_name,
                tree_sha[:7],
                resp.status_code,
            )
            return []
        data = resp.json()
        if data.get("truncated"):
            logger.warning(
                "repo tree truncated for %s — large repo, context may be incomplete",
                repo_name,
            )
        paths = [item["path"] for item in data.get("tree", []) if item.get("type") == "blob"]
        logger.info("fetch_repo_tree: %d files for %s@%s", len(paths), repo_name, tree_sha[:7])
        return paths

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def post_pr_comment(self, repo_name: str, pr_number: int, body: str) -> bool:
        """Post a general comment on a GitHub PR (fallback for inline failures).

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
