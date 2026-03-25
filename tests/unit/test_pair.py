"""Tests for functions/devices/pair/handler.py

POST /v1/devices/pair — validates a pairing code and activates the device,
returning the raw device token exactly once.
"""
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import FakeContext, make_sm_client


# ---------------------------------------------------------------------------
# Module import helper
# The handler calls boto3.client("secretsmanager") at module level, so we must
# patch boto3.client before importing the module.
# ---------------------------------------------------------------------------

def _import_handler():
    """(Re-)import the pair handler with the SM client already patched."""
    mod_name = "functions.devices.pair.handler"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    with patch("boto3.client", side_effect=lambda svc, **kw: make_sm_client() if svc == "secretsmanager" else MagicMock()):
        import importlib.util, os
        spec = importlib.util.spec_from_file_location(
            mod_name,
            os.path.join(os.path.dirname(__file__), "../../functions/devices/pair/handler.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod


@pytest.fixture()
def handler_mod():
    mod = _import_handler()
    yield mod
    if "functions.devices.pair.handler" in sys.modules:
        del sys.modules["functions.devices.pair.handler"]


def _make_rds(*, updated: int = 1, device_id: str = "device-uuid-1") -> MagicMock:
    rds = MagicMock()
    rds.execute_statement.return_value = {
        "numberOfRecordsUpdated": updated,
        "records": [[{"stringValue": device_id}]] if updated else [],
    }
    return rds


def _event(body: dict) -> dict:
    return {"httpMethod": "POST", "headers": {}, "body": json.dumps(body)}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPairHandler:
    def test_options_returns_204(self, handler_mod):
        event = {"httpMethod": "OPTIONS", "headers": {}, "body": None}
        resp = handler_mod.handler(event, FakeContext())
        assert resp["statusCode"] == 204

    def test_happy_path_returns_device_token(self, handler_mod):
        rds = _make_rds(updated=1)
        with patch("boto3.client", return_value=rds):
            resp = handler_mod.handler(
                _event({"pairing_code": "VALIDCODE123"}), FakeContext()
            )
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert "device_token" in body
        assert len(body["device_token"]) == 64  # secrets.token_hex(32)

    def test_missing_pairing_code_returns_400(self, handler_mod):
        rds = _make_rds()
        with patch("boto3.client", return_value=rds):
            resp = handler_mod.handler(_event({}), FakeContext())
        assert resp["statusCode"] == 400
        assert "pairing_code" in json.loads(resp["body"])["error"]

    def test_pairing_code_too_long_returns_400(self, handler_mod):
        rds = _make_rds()
        with patch("boto3.client", return_value=rds):
            resp = handler_mod.handler(
                _event({"pairing_code": "X" * 65}), FakeContext()
            )
        assert resp["statusCode"] == 400

    def test_pairing_code_too_short_returns_400(self, handler_mod):
        rds = _make_rds()
        with patch("boto3.client", return_value=rds):
            resp = handler_mod.handler(
                _event({"pairing_code": "X" * 5}), FakeContext()
            )
        assert resp["statusCode"] == 400
        assert "short" in json.loads(resp["body"])["error"]

    def test_invalid_or_expired_code_returns_400(self, handler_mod):
        rds = _make_rds(updated=0)
        with patch("boto3.client", return_value=rds):
            resp = handler_mod.handler(
                _event({"pairing_code": "BADCODE"}), FakeContext()
            )
        assert resp["statusCode"] == 400
        assert "Invalid" in json.loads(resp["body"])["error"]

    def test_invalid_json_body_returns_400(self, handler_mod):
        event = {"httpMethod": "POST", "headers": {}, "body": "not-json"}
        rds = _make_rds()
        with patch("boto3.client", return_value=rds):
            resp = handler_mod.handler(event, FakeContext())
        assert resp["statusCode"] == 400

    def test_aws_failure_returns_500(self, handler_mod):
        rds = MagicMock()
        rds.execute_statement.side_effect = Exception("DB connection refused")
        with patch("boto3.client", return_value=rds):
            resp = handler_mod.handler(
                _event({"pairing_code": "VALIDCODE123"}), FakeContext()
            )
        assert resp["statusCode"] == 500

    def test_cors_headers_present(self, handler_mod):
        rds = _make_rds(updated=1)
        with patch("boto3.client", return_value=rds):
            resp = handler_mod.handler(
                _event({"pairing_code": "VALIDCODE123"}), FakeContext()
            )
        assert "Access-Control-Allow-Origin" in resp["headers"]

    def test_pairing_code_hashed_before_db_lookup(self, handler_mod):
        """The submitted pairing code must be hashed before the WHERE clause — not compared as plaintext."""
        rds = _make_rds(updated=1)
        plaintext_code = "VALIDCODE123"
        with patch("boto3.client", return_value=rds):
            resp = handler_mod.handler(_event({"pairing_code": plaintext_code}), FakeContext())

        assert resp["statusCode"] == 200

        update_call = next(
            c for c in rds.execute_statement.call_args_list
            if "UPDATE devices" in c.kwargs.get("sql", "")
        )
        params = {p["name"]: p["value"]["stringValue"] for p in update_call.kwargs["parameters"]}
        assert params["code"] != plaintext_code, "plaintext code must not reach the DB"
        assert len(params["code"]) == 64, "expected HMAC-SHA256 hex digest (64 chars)"
