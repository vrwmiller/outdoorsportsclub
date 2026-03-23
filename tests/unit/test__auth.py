"""Unit tests for functions/shared/_auth.py

Covers two areas added in the JWT hardening PR (Issues #74, #75, #76):

  validate_cognito_jwt():
    - success path returns decoded claims
    - iss mismatch raises PermissionError       (#75)
    - token_use != "access" raises PermissionError  (#74)
    - client_id mismatch raises PermissionError     (#74)
    - expired token raises PermissionError
    - unknown kid triggers a force-refresh then fails cleanly (#76)

  _get_jwks():
    - fetches JWKS on first call
    - reuses cached value within the 1-hour TTL      (#76)
    - fetches again after the TTL has expired         (#76)
    - force_refresh=True bypasses the TTL             (#76)
"""
import importlib.util
import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import jwt
import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

# ---------------------------------------------------------------------------
# Module-level RSA key material — generated once for the test session.
# ---------------------------------------------------------------------------

_PRIVATE_KEY = rsa.generate_private_key(
    public_exponent=65537, key_size=2048, backend=default_backend()
)
_PUBLIC_KEY = _PRIVATE_KEY.public_key()
_TEST_KID = "test-key-id-1"
_JWK = {**json.loads(RSAAlgorithm.to_jwk(_PUBLIC_KEY)), "kid": _TEST_KID}
_FAKE_JWKS = {"keys": [_JWK]}

# These values must match the conftest.py lambda_env autouse fixture.
_POOL_ID = "us-east-1_TestPool"
_REGION = "us-east-1"
_CLIENT_ID = "test-app-client-id"
_EXPECTED_ISS = f"https://cognito-idp.{_REGION}.amazonaws.com/{_POOL_ID}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mint_token(overrides: dict | None = None) -> str:
    """Return a valid RS256-signed JWT using the test key pair."""
    claims = {
        "sub": "test-sub-123",
        "iss": _EXPECTED_ISS,
        "token_use": "access",
        "client_id": _CLIENT_ID,
        "exp": int(time.time()) + 3600,
    }
    if overrides:
        claims.update(overrides)
    return jwt.encode(claims, _PRIVATE_KEY, algorithm="RS256", headers={"kid": _TEST_KID})


def _make_urlopen_mock(payload: dict) -> MagicMock:
    """Return a MagicMock for urllib.request.urlopen that yields the given JSON payload."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(payload).encode()
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_resp
    mock_cm.__exit__.return_value = False
    return MagicMock(return_value=mock_cm)


# ---------------------------------------------------------------------------
# Fixture: freshly loaded _auth module for each test.
#
# _auth.py resolves env vars and wires module-level constants at import time,
# so we reload it per-test to pick up the lambda_env monkeypatches and to
# reset the JWKS cache globals (_jwks_cache, _jwks_fetched_at).
# ---------------------------------------------------------------------------

@pytest.fixture()
def auth(lambda_env):  # lambda_env is autouse but listed explicitly to enforce ordering
    """Load functions/shared/_auth.py fresh with boto3 patched."""
    auth_path = Path(__file__).parent.parent.parent / "functions" / "shared" / "_auth.py"
    sys.modules.pop("_auth", None)

    with patch("boto3.client", return_value=MagicMock()):
        spec = importlib.util.spec_from_file_location("_auth", auth_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_auth"] = mod
        spec.loader.exec_module(mod)

    yield mod
    sys.modules.pop("_auth", None)


# ---------------------------------------------------------------------------
# Tests: validate_cognito_jwt()
# ---------------------------------------------------------------------------

class TestValidateCognitoJwt:
    def test_valid_token_returns_claims(self, auth):
        token = _mint_token()
        with patch.object(auth, "_get_jwks", return_value=_FAKE_JWKS):
            claims = auth.validate_cognito_jwt(token)
        assert claims["sub"] == "test-sub-123"
        assert claims["client_id"] == _CLIENT_ID

    def test_issuer_mismatch_raises(self, auth):
        token = _mint_token({"iss": "https://cognito-idp.us-east-1.amazonaws.com/wrong-pool"})
        with patch.object(auth, "_get_jwks", return_value=_FAKE_JWKS):
            with pytest.raises(PermissionError, match="issuer"):
                auth.validate_cognito_jwt(token)

    def test_token_use_id_token_raises(self, auth):
        token = _mint_token({"token_use": "id"})
        with patch.object(auth, "_get_jwks", return_value=_FAKE_JWKS):
            with pytest.raises(PermissionError, match="token_use"):
                auth.validate_cognito_jwt(token)

    def test_client_id_mismatch_raises(self, auth):
        token = _mint_token({"client_id": "other-client-id"})
        with patch.object(auth, "_get_jwks", return_value=_FAKE_JWKS):
            with pytest.raises(PermissionError, match="client_id"):
                auth.validate_cognito_jwt(token)

    def test_expired_token_raises(self, auth):
        token = _mint_token({"exp": int(time.time()) - 60})
        with patch.object(auth, "_get_jwks", return_value=_FAKE_JWKS):
            with pytest.raises(PermissionError, match="expired"):
                auth.validate_cognito_jwt(token)

    def test_unknown_kid_force_refreshes_then_fails(self, auth):
        """On kid-not-found, _get_jwks is called a second time with force_refresh=True."""
        wrong_jwks = {"keys": [{**_JWK, "kid": "other-kid"}]}
        mock_get = MagicMock(return_value=wrong_jwks)
        with patch.object(auth, "_get_jwks", mock_get):
            with pytest.raises(PermissionError, match="key ID not found"):
                auth.validate_cognito_jwt(_mint_token())
        assert mock_get.call_count == 2
        assert mock_get.call_args_list[1] == call(force_refresh=True)


# ---------------------------------------------------------------------------
# Tests: _get_jwks() TTL + force-refresh caching logic
# ---------------------------------------------------------------------------

class TestGetJwks:
    def test_fetches_on_first_call(self, auth):
        auth._jwks_cache = None
        auth._jwks_fetched_at = 0.0
        mock_open = _make_urlopen_mock(_FAKE_JWKS)
        with patch("urllib.request.urlopen", mock_open):
            result = auth._get_jwks()
        mock_open.assert_called_once()
        assert result == _FAKE_JWKS

    def test_reuses_cache_within_ttl(self, auth):
        auth._jwks_cache = _FAKE_JWKS
        auth._jwks_fetched_at = time.time() - 100  # 100 s ago — well within the 1-hour TTL
        mock_open = _make_urlopen_mock({"keys": []})
        with patch("urllib.request.urlopen", mock_open):
            result = auth._get_jwks()
        mock_open.assert_not_called()
        assert result is _FAKE_JWKS

    def test_refreshes_after_ttl_expires(self, auth):
        new_jwks = {"keys": [{"kid": "new-key"}]}
        auth._jwks_cache = {"keys": [{"kid": "old-key"}]}
        auth._jwks_fetched_at = time.time() - 4000  # 4000 s ago — past the 1-hour TTL
        mock_open = _make_urlopen_mock(new_jwks)
        with patch("urllib.request.urlopen", mock_open):
            result = auth._get_jwks()
        mock_open.assert_called_once()
        assert result == new_jwks

    def test_force_refresh_bypasses_ttl(self, auth):
        new_jwks = {"keys": [{"kid": "refreshed-key"}]}
        auth._jwks_cache = {"keys": [{"kid": "old-key"}]}
        auth._jwks_fetched_at = time.time() - 100  # within TTL — bypass it anyway
        mock_open = _make_urlopen_mock(new_jwks)
        with patch("urllib.request.urlopen", mock_open):
            result = auth._get_jwks(force_refresh=True)
        mock_open.assert_called_once()
        assert result == new_jwks
