import os

import requests
from dotenv import load_dotenv

load_dotenv()

_GITHUB_API = "https://api.github.com"


def _headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN environment variable is not set")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def fetch_file_content(repo_name: str, file_path: str, ref: str = "main") -> str:
    """Fetch the raw content of a file from GitHub.

    Args:
        repo_name: e.g. "owner/repo"
        file_path: path inside the repo, e.g. "src/utils.py"
        ref: branch or commit SHA

    Returns:
        Raw file content as a string, or an error message.
    """
    url = f"{_GITHUB_API}/repos/{repo_name}/contents/{file_path}"
    resp = requests.get(url, headers=_headers(), params={"ref": ref}, timeout=10)
    if resp.status_code != 200:
        return f"[Error fetching {file_path}: HTTP {resp.status_code}]"

    import base64

    data = resp.json()
    if data.get("encoding") == "base64":
        return base64.b64decode(data["content"]).decode("utf-8")
    return data.get("content", "")


def post_pr_comment(repo_name: str, pr_number: int, body: str) -> bool:
    """Post a review comment on a GitHub PR.

    Args:
        repo_name: e.g. "owner/repo"
        pr_number: the PR number
        body: Markdown comment body

    Returns:
        True if successful, False otherwise.
    """
    url = f"{_GITHUB_API}/repos/{repo_name}/issues/{pr_number}/comments"
    resp = requests.post(url, headers=_headers(), json={"body": body}, timeout=10)
    return resp.status_code == 201
