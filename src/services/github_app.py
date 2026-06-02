import logging
import time
from pathlib import Path

import jwt
import requests
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config.settings import settings

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"


def _load_private_key() -> str:
    """Load the GitHub App private key from PEM content or file path."""
    key = settings.github_app_private_key
    if not key:
        raise ValueError("GITHUB_APP_PRIVATE_KEY is not configured")

    # If it looks like a file path, load the file content
    if key.endswith(".pem") or key.startswith("/") or key.startswith("./"):
        path = Path(key)
        if path.is_file():
            return path.read_text(encoding="utf-8")
        raise ValueError(f"GITHUB_APP_PRIVATE_KEY file not found: {key}")

    return key


def _generate_app_jwt() -> str:
    """Generate a JWT for GitHub App authentication.

    The JWT is signed with RS256 and valid for 10 minutes.
    """
    now = int(time.time())
    payload = {
        "iat": now - 60,  # issued at (60s leeway for clock drift)
        "exp": now + (10 * 60),  # expires at (10 min)
        "iss": settings.github_app_id,
    }
    private_key = _load_private_key()
    return jwt.encode(payload, private_key, algorithm="RS256")


class GitHubAppService:
    """Service for GitHub App JWT authentication and token exchange."""

    @staticmethod
    def _headers() -> dict:
        return {
            "Authorization": f"Bearer {_generate_app_jwt()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception_type(requests.RequestException),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def get_installation_access_token(self, installation_id: int) -> str:
        """Exchange a GitHub App JWT for an installation access token.

        Args:
            installation_id: The installation ID from the webhook payload.

        Returns:
            The installation access token string.
        """
        url = f"{_GITHUB_API}/app/installations/{installation_id}/access_tokens"
        resp = requests.post(url, headers=self._headers(), timeout=10)

        if resp.status_code != 201:
            raise RuntimeError(f"Failed to get installation access token: HTTP {resp.status_code} - {resp.text}")

        token = resp.json()["token"]
        logger.info("Obtained installation access token for installation %d", installation_id)
        return token


def get_installation_access_token(installation_id: int) -> str:
    """Convenience wrapper around ``GitHubAppService``."""
    return GitHubAppService().get_installation_access_token(installation_id)
