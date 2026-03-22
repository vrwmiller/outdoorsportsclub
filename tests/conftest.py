"""Shared pytest fixtures for Lambda handler unit tests.

All handlers (and _auth.py) call boto3.client("secretsmanager") at module level
to fetch the DEVICE_TOKEN_SALT during the Lambda cold-start.  To avoid real AWS
calls, tests import handler modules via helper loaders (for example,
``load_kiosk_handler()``) that patch boto3.client *before* the module is imported.
"""
import hashlib
import hmac
import importlib.util
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fake secrets / salts used across all tests
# ---------------------------------------------------------------------------

FAKE_SALT = "deadbeef" * 4  # 32-char hex string
FAKE_STRIPE_KEY = "sk_test_fakekey"
FAKE_DEVICE_TOKEN_SALT_SECRET = json.dumps({"salt": FAKE_SALT})
FAKE_STRIPE_SECRET = FAKE_STRIPE_KEY

# A valid raw device token whose HMAC-SHA256 we pre-compute once.
RAW_TOKEN = "myrawdevicetoken"
HASHED_TOKEN = hmac.new(FAKE_SALT.encode(), RAW_TOKEN.encode(), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_sm_client() -> MagicMock:
    """Return a mock secretsmanager client that returns canned secrets."""

    def _get_secret_value(SecretId: str, **_):
        if "stripe" in SecretId.lower():
            return {"SecretString": FAKE_STRIPE_KEY}
        return {"SecretString": FAKE_DEVICE_TOKEN_SALT_SECRET}

    sm = MagicMock()
    sm.get_secret_value.side_effect = _get_secret_value
    return sm


def device_event(body: dict | None = None, path_params: dict | None = None) -> dict:
    """Build a minimal API Gateway event with a valid device token header."""
    return {
        "httpMethod": "POST",
        "headers": {"x-device-token": RAW_TOKEN},
        "body": json.dumps(body or {}),
        "pathParameters": path_params or {},
    }


def active_device_row():
    """RDS record for an active device with a known range."""
    return [
        {"stringValue": "device-id-1"},
        {"stringValue": "range-id-1"},
        {"stringValue": "Active"},
    ]


class FakeContext:
    aws_request_id = "test-request-id"


# ---------------------------------------------------------------------------
# Environment variables
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def lambda_env(monkeypatch):
    """Set all required Lambda environment variables before each test."""
    monkeypatch.setenv("DB_CLUSTER_ARN", "arn:aws:rds:us-east-1:123456789012:cluster:test")
    monkeypatch.setenv("DB_SECRET_ARN", "arn:aws:secretsmanager:us-east-1:123456789012:secret:db")
    monkeypatch.setenv("DB_NAME", "outdoorsportsclub")
    monkeypatch.setenv("DEVICE_TOKEN_SALT_ARN", "arn:aws:secretsmanager:us-east-1:123456789012:secret:salt")
    monkeypatch.setenv("CORS_ALLOW_ORIGIN", "http://localhost:3000")
    monkeypatch.setenv("STRIPE_SECRET_ARN", "arn:aws:secretsmanager:us-east-1:123456789012:secret:stripe")
    monkeypatch.setenv("S3_WAIVER_BUCKET", "test-waiver-bucket")
    monkeypatch.setenv("SNS_ALERTS_TOPIC_ARN", "arn:aws:sns:us-east-1:123456789012:test-alerts")
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_TestPool")
    monkeypatch.setenv("COGNITO_REGION", "us-east-1")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")


# ---------------------------------------------------------------------------
# Kiosk module loader
# _auth.py (and every kiosk handler) calls boto3.client("secretsmanager") at
# module level, so we must patch boto3.client *before* importing any kiosk
# module.  Call load_kiosk_handler() inside a test to get the handler module.
# ---------------------------------------------------------------------------

def _kiosk_boto_factory(svc, **_):
    """Return mocked AWS clients for kiosk cold-start imports."""
    if svc == "secretsmanager":
        return make_sm_client()
    return MagicMock()


def load_kiosk_handler(subpath: str):
    """Import a kiosk handler module with boto3 patched for cold-start.

    ``subpath`` is the directory name under functions/kiosk/, e.g. "checkin".
    Returns the imported module.  The caller is responsible for removing
    the module from sys.modules after the test.
    """
    kiosk_dir = os.path.join(os.path.dirname(__file__), "../functions/kiosk")
    handler_path = os.path.join(kiosk_dir, subpath, "handler.py")
    mod_name = f"kiosk_{subpath}_handler"

    # Ensure _auth can be found via bare import
    if kiosk_dir not in sys.path:
        sys.path.insert(0, kiosk_dir)

    # Evict any previously cached versions
    for key in list(sys.modules.keys()):
        if key in ("_auth", mod_name):
            del sys.modules[key]

    with patch("boto3.client", side_effect=_kiosk_boto_factory):
        # Import _auth first so the salt is cached
        auth_spec = importlib.util.spec_from_file_location("_auth", os.path.join(kiosk_dir, "_auth.py"))
        auth_mod = importlib.util.module_from_spec(auth_spec)
        sys.modules["_auth"] = auth_mod
        auth_spec.loader.exec_module(auth_mod)

        spec = importlib.util.spec_from_file_location(mod_name, handler_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)

    return mod


# ---------------------------------------------------------------------------
# Fake JWT claims used across member and admin tests
# ---------------------------------------------------------------------------

FAKE_SUB = "cognito-sub-test-1234"
FAKE_MEMBER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FAKE_MEMBER_CLAIMS = {"sub": FAKE_SUB, "email": "test@example.com"}


def member_jwt_event(
    body: dict | None = None,
    path_params: dict | None = None,
    method: str = "GET",
) -> dict:
    """Build a minimal API Gateway event with an Authorization: Bearer header.

    The token value is intentionally fake — tests must patch
    ``validate_cognito_jwt`` in the handler module to return FAKE_MEMBER_CLAIMS.
    """
    return {
        "httpMethod": method,
        "headers": {"Authorization": "Bearer fake.jwt.token"},
        "body": json.dumps(body) if body is not None else None,
        "pathParameters": path_params or {},
    }


def _member_auth_boto_factory(svc, **_):
    """Return mocked AWS clients for member/admin _auth cold-start imports.

    _auth.py reads env vars at module level (no boto3 cold-start call), so
    this factory only needs to provide the rds-data client used during
    authenticate_member().
    """
    return MagicMock()


def load_member_handler(subpath: str):
    """Import a member handler module with boto3 patched for cold-start.

    ``subpath`` is the directory name under functions/members/, e.g. "me".
    The caller must also patch ``validate_cognito_jwt`` in the returned
    module before invoking handler() in tests.
    Returns the imported module.
    """
    members_dir = os.path.join(os.path.dirname(__file__), "../functions/members")
    shared_dir = os.path.join(os.path.dirname(__file__), "../functions/shared")
    handler_path = os.path.join(members_dir, subpath, "handler.py")
    mod_name = f"member_{subpath.replace('-', '_')}_handler"

    if members_dir not in sys.path:
        sys.path.insert(0, members_dir)

    for key in list(sys.modules.keys()):
        if key in ("_auth", mod_name):
            del sys.modules[key]

    with patch("boto3.client", side_effect=_member_auth_boto_factory):
        auth_spec = importlib.util.spec_from_file_location(
            "_auth", os.path.join(shared_dir, "_auth.py")
        )
        auth_mod = importlib.util.module_from_spec(auth_spec)
        sys.modules["_auth"] = auth_mod
        auth_spec.loader.exec_module(auth_mod)

        spec = importlib.util.spec_from_file_location(mod_name, handler_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)

    return mod


def load_admin_handler(subpath: str):
    """Import an admin handler module with boto3 patched for cold-start.

    ``subpath`` is the directory name under functions/admin/, e.g. "settings-get".
    Returns the imported module.
    """
    admin_dir = os.path.join(os.path.dirname(__file__), "../functions/admin")
    shared_dir = os.path.join(os.path.dirname(__file__), "../functions/shared")
    handler_path = os.path.join(admin_dir, subpath, "handler.py")
    mod_name = f"admin_{subpath.replace('-', '_')}_handler"

    if admin_dir not in sys.path:
        sys.path.insert(0, admin_dir)

    for key in list(sys.modules.keys()):
        if key in ("_auth", mod_name):
            del sys.modules[key]

    with patch("boto3.client", side_effect=_member_auth_boto_factory):
        auth_spec = importlib.util.spec_from_file_location(
            "_auth", os.path.join(shared_dir, "_auth.py")
        )
        auth_mod = importlib.util.module_from_spec(auth_spec)
        sys.modules["_auth"] = auth_mod
        auth_spec.loader.exec_module(auth_mod)

        spec = importlib.util.spec_from_file_location(mod_name, handler_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)

    return mod
