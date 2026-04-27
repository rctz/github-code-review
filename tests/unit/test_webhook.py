import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from entrypoints.webhook import REVIEW_TRIGGER_ACTIONS, _verify_signature, app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _make_signature(secret: str, body: bytes) -> str:
    """Create a valid HMAC-SHA256 signature matching GitHub's format."""
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


class TestVerifySignature:
    def test_valid_signature_returns_true(self) -> None:
        secret = "test-secret"
        body = b'{"action": "opened"}'
        sig = _make_signature(secret, body)
        with patch("entrypoints.webhook.settings") as mock_settings:
            mock_settings.github_webhook_secret = secret
            assert _verify_signature(body, sig) is True

    def test_invalid_signature_returns_false(self) -> None:
        secret = "test-secret"
        body = b'{"action": "opened"}'
        with patch("entrypoints.webhook.settings") as mock_settings:
            mock_settings.github_webhook_secret = secret
            assert _verify_signature(body, "sha256=deadbeef00000000") is False

    def test_missing_secret_raises_500(self) -> None:
        from fastapi import HTTPException

        with patch("entrypoints.webhook.settings") as mock_settings:
            mock_settings.github_webhook_secret = ""
            with pytest.raises(HTTPException) as exc_info:
                _verify_signature(b"body", "sha256=anything")
            assert exc_info.value.status_code == 500


class TestHealthEndpoint:
    def test_returns_ok(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestWebhookEndpoint:
    def _post(
        self,
        client: TestClient,
        payload: dict,
        *,
        event: str = "pull_request",
        secret: str = "",
        bad_sig: bool = False,
    ):
        body = json.dumps(payload).encode()
        headers = {"x-github-event": event, "content-type": "application/json"}
        if secret:
            sig = "sha256=badsig" if bad_sig else _make_signature(secret, body)
            headers["x-hub-signature-256"] = sig
        return client.post("/webhook", content=body, headers=headers)

    @patch("entrypoints.webhook.settings")
    def test_non_pr_event_ignored(self, mock_settings: MagicMock, client: TestClient) -> None:
        mock_settings.github_webhook_secret = ""
        mock_settings.log_level = "INFO"
        resp = self._post(client, {"action": "created"}, event="push")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"
        assert "push" in resp.json()["reason"]

    @patch("entrypoints.webhook.settings")
    def test_pr_non_trigger_action_ignored(self, mock_settings: MagicMock, client: TestClient) -> None:
        mock_settings.github_webhook_secret = ""
        mock_settings.log_level = "INFO"
        payload = {
            "action": "closed",
            "pull_request": {"number": 1},
            "repository": {"name": "repo", "owner": {"login": "owner"}},
        }
        resp = self._post(client, payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    @patch("entrypoints.webhook.settings")
    def test_invalid_signature_returns_401(self, mock_settings: MagicMock, client: TestClient) -> None:
        mock_settings.github_webhook_secret = "real-secret"
        mock_settings.log_level = "INFO"
        payload = {
            "action": "opened",
            "pull_request": {"number": 1},
            "repository": {"name": "repo", "owner": {"login": "owner"}},
        }
        resp = self._post(client, payload, secret="real-secret", bad_sig=True)
        assert resp.status_code == 401

    @patch("entrypoints.webhook._process_review")
    @patch("entrypoints.webhook.settings")
    def test_valid_signature_accepted(
        self, mock_settings: MagicMock, mock_process: MagicMock, client: TestClient
    ) -> None:
        secret = "correct-secret"
        mock_settings.github_webhook_secret = secret
        mock_settings.log_level = "INFO"
        payload = {
            "action": "opened",
            "pull_request": {"number": 7},
            "repository": {"name": "my-repo", "owner": {"login": "my-org"}},
        }
        resp = self._post(client, payload, secret=secret)
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    @patch("entrypoints.webhook._process_review")
    @patch("entrypoints.webhook.settings")
    def test_trigger_actions_accepted(
        self, mock_settings: MagicMock, mock_process: MagicMock, client: TestClient
    ) -> None:
        mock_settings.github_webhook_secret = ""
        mock_settings.log_level = "INFO"
        for action in REVIEW_TRIGGER_ACTIONS:
            payload = {
                "action": action,
                "pull_request": {"number": 1},
                "repository": {"name": "r", "owner": {"login": "o"}},
            }
            resp = self._post(client, payload)
            assert resp.status_code == 200, f"action={action} should be accepted"
            assert resp.json()["status"] == "accepted", f"action={action}"

    @patch("entrypoints.webhook._process_review")
    @patch("entrypoints.webhook.settings")
    def test_accepted_response_contains_repo_and_pr(
        self, mock_settings: MagicMock, mock_process: MagicMock, client: TestClient
    ) -> None:
        mock_settings.github_webhook_secret = ""
        mock_settings.log_level = "INFO"
        payload = {
            "action": "opened",
            "pull_request": {"number": 42},
            "repository": {"name": "cool-repo", "owner": {"login": "acme"}},
        }
        resp = self._post(client, payload)
        data = resp.json()
        assert data["pr"] == 42
        assert "acme/cool-repo" in data["repo"]
