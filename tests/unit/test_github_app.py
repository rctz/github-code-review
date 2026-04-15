import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from services.github_app import _generate_app_jwt, _load_private_key, get_installation_access_token


def _make_test_rsa_key() -> str:
    """Generate a temporary RSA private key (PEM) for testing."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


_TEST_PRIVATE_KEY = _make_test_rsa_key()


class TestLoadPrivateKey:
    @patch("services.github_app.settings")
    def test_returns_pem_content_directly(self, mock_settings: MagicMock) -> None:
        mock_settings.github_app_private_key = _TEST_PRIVATE_KEY
        result = _load_private_key()
        assert result == _TEST_PRIVATE_KEY

    @patch("services.github_app.settings")
    def test_raises_when_not_configured(self, mock_settings: MagicMock) -> None:
        mock_settings.github_app_private_key = ""
        with pytest.raises(ValueError, match="GITHUB_APP_PRIVATE_KEY"):
            _load_private_key()

    @patch("services.github_app.settings")
    def test_loads_from_file_path(self, mock_settings: MagicMock, tmp_path) -> None:
        pem_file = tmp_path / "key.pem"
        pem_file.write_text(_TEST_PRIVATE_KEY)
        mock_settings.github_app_private_key = str(pem_file)
        result = _load_private_key()
        assert result == _TEST_PRIVATE_KEY

    @patch("services.github_app.settings")
    def test_missing_file_raises(self, mock_settings: MagicMock) -> None:
        mock_settings.github_app_private_key = "/nonexistent/path/key.pem"
        with pytest.raises(ValueError, match="not found"):
            _load_private_key()


class TestGenerateAppJwt:
    @patch("services.github_app.settings")
    def test_returns_valid_jwt(self, mock_settings: MagicMock) -> None:
        mock_settings.github_app_id = "123456"
        mock_settings.github_app_private_key = _TEST_PRIVATE_KEY

        token = _generate_app_jwt()

        # Decode without verification to inspect claims
        claims = jwt.decode(token, options={"verify_signature": False})
        assert claims["iss"] == "123456"

    @patch("services.github_app.settings")
    def test_jwt_expiry_is_10_minutes(self, mock_settings: MagicMock) -> None:
        mock_settings.github_app_id = "999"
        mock_settings.github_app_private_key = _TEST_PRIVATE_KEY

        before = int(time.time())
        token = _generate_app_jwt()
        after = int(time.time())

        claims = jwt.decode(token, options={"verify_signature": False})
        # exp should be ~10 minutes from now
        assert before + 9 * 60 <= claims["exp"] <= after + 10 * 60

    @patch("services.github_app.settings")
    def test_jwt_iat_has_60s_leeway(self, mock_settings: MagicMock) -> None:
        mock_settings.github_app_id = "999"
        mock_settings.github_app_private_key = _TEST_PRIVATE_KEY

        now = int(time.time())
        token = _generate_app_jwt()

        claims = jwt.decode(token, options={"verify_signature": False})
        # iat should be 60 seconds before now (clock drift leeway)
        assert claims["iat"] <= now - 55  # allow a few seconds tolerance

    @patch("services.github_app.settings")
    def test_jwt_signed_with_rs256(self, mock_settings: MagicMock) -> None:
        mock_settings.github_app_id = "42"
        mock_settings.github_app_private_key = _TEST_PRIVATE_KEY

        token = _generate_app_jwt()

        header = jwt.get_unverified_header(token)
        assert header["alg"] == "RS256"


class TestGetInstallationAccessToken:
    @patch("services.github_app.requests")
    @patch("services.github_app.settings")
    def test_returns_token_on_success(self, mock_settings: MagicMock, mock_requests: MagicMock) -> None:
        mock_settings.github_app_id = "123"
        mock_settings.github_app_private_key = _TEST_PRIVATE_KEY

        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"token": "ghs_test_token_abc"}
        mock_requests.post.return_value = mock_resp

        result = get_installation_access_token(installation_id=42)

        assert result == "ghs_test_token_abc"
        mock_requests.post.assert_called_once()
        url = mock_requests.post.call_args[0][0]
        assert "42" in url
        assert "access_tokens" in url

    @patch("services.github_app.requests")
    @patch("services.github_app.settings")
    def test_raises_on_api_error(self, mock_settings: MagicMock, mock_requests: MagicMock) -> None:
        mock_settings.github_app_id = "123"
        mock_settings.github_app_private_key = _TEST_PRIVATE_KEY

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        mock_requests.post.return_value = mock_resp

        with pytest.raises(RuntimeError, match="401"):
            get_installation_access_token(installation_id=99)

    @patch("services.github_app.requests")
    @patch("services.github_app.settings")
    def test_request_uses_bearer_auth(self, mock_settings: MagicMock, mock_requests: MagicMock) -> None:
        mock_settings.github_app_id = "123"
        mock_settings.github_app_private_key = _TEST_PRIVATE_KEY

        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"token": "tok"}
        mock_requests.post.return_value = mock_resp

        get_installation_access_token(installation_id=1)

        headers = mock_requests.post.call_args[1]["headers"]
        assert headers["Authorization"].startswith("Bearer ")
