"""Tests for functions/admin/devices-pairing-code/handler.py

POST /v1/admin/devices/pairing-code — Level 6 creates a new device pairing.
"""
import json
import sys
from unittest.mock import patch

import pytest

from tests.conftest import (
    FAKE_MEMBER_ID,
    FAKE_SUB,
    FakeContext,
    member_jwt_event,
    load_admin_handler,
)
from tests.helpers import make_member_rds

_WEBMASTER = {"member_id": FAKE_MEMBER_ID, "sub": FAKE_SUB, "training_level": 6}

_MOD_NAME = "admin_devices_pairing_code_handler"

_DEVICE_ID = "dddddddd-eeee-ffff-0000-111111111111"

_GOOD_RANGE_ID = "11111111-2222-3333-4444-555555555555"
_GOOD_BODY = {"location_tag": "kiosk-main", "range_id": _GOOD_RANGE_ID}


@pytest.fixture()
def mod():
    m = load_admin_handler("devices-pairing-code")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", _MOD_NAME):
            del sys.modules[key]


class TestAdminDevicesPairingCode:
    def test_success_returns_201(self, mod):
        rds = make_member_rds({
            "pairing_code IS NOT NULL": {"records": []},  # no existing unexpired code
            "INSERT INTO devices": {"records": [[{"stringValue": _DEVICE_ID}]]},
        })
        with patch.object(mod, "authenticate_member", return_value=_WEBMASTER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(member_jwt_event(_GOOD_BODY, method="POST"), FakeContext())

        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert body["device_id"] == _DEVICE_ID
        assert "pairing_code" in body
        assert len(body["pairing_code"]) == 8
        assert body["pairing_code"].isupper() or body["pairing_code"].isalnum()
        assert "expires_at" in body

    def test_conflict_returns_409(self, mod):
        rds = make_member_rds({
            "pairing_code IS NOT NULL": {"records": [[{"stringValue": "existing-device-id"}]]},
        })
        with patch.object(mod, "authenticate_member", return_value=_WEBMASTER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(member_jwt_event(_GOOD_BODY, method="POST"), FakeContext())

        assert resp["statusCode"] == 409

    def test_missing_location_tag_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_WEBMASTER):
            resp = mod.handler(
                member_jwt_event({"range_id": "range-id-1"}, method="POST"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_missing_range_id_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_WEBMASTER):
            resp = mod.handler(
                member_jwt_event({"location_tag": "kiosk-main"}, method="POST"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_invalid_range_id_uuid_returns_400(self, mod):
        """Non-UUID range_id must be rejected before hitting the DB."""
        with patch.object(mod, "authenticate_member", return_value=_WEBMASTER):
            resp = mod.handler(
                member_jwt_event(
                    {"location_tag": "kiosk-main", "range_id": "not-a-uuid"},
                    method="POST",
                ),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_numeric_range_id_returns_400(self, mod):
        """range_id supplied as a JSON number (not a string) must return 400, not 500."""
        with patch.object(mod, "authenticate_member", return_value=_WEBMASTER):
            resp = mod.handler(
                member_jwt_event({"location_tag": "kiosk-main", "range_id": 12345}, method="POST"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_level_5_returns_403(self, mod):
        low = {"member_id": FAKE_MEMBER_ID, "sub": FAKE_SUB, "training_level": 5}
        with patch.object(mod, "authenticate_member", return_value=low):
            resp = mod.handler(member_jwt_event(_GOOD_BODY, method="POST"), FakeContext())

        assert resp["statusCode"] == 403

    def test_auth_failure_returns_403(self, mod):
        with patch.object(mod, "authenticate_member", side_effect=PermissionError("denied")):
            resp = mod.handler(member_jwt_event(_GOOD_BODY, method="POST"), FakeContext())

        assert resp["statusCode"] == 403

    def test_cors_headers_present(self, mod):
        rds = make_member_rds({
            "pairing_code IS NOT NULL": {"records": []},
            "INSERT INTO devices": {"records": [[{"stringValue": _DEVICE_ID}]]},
        })
        with patch.object(mod, "authenticate_member", return_value=_WEBMASTER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(member_jwt_event(_GOOD_BODY, method="POST"), FakeContext())

        assert "Access-Control-Allow-Origin" in resp["headers"]

    def test_pairing_code_stored_as_hmac_not_plaintext(self, mod):
        """The code written to devices.pairing_code must be an HMAC hash, not the raw code."""
        rds = make_member_rds({
            "pairing_code IS NOT NULL": {"records": []},
            "INSERT INTO devices": {"records": [[{"stringValue": _DEVICE_ID}]]},
        })
        with patch.object(mod, "authenticate_member", return_value=_WEBMASTER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(member_jwt_event(_GOOD_BODY, method="POST"), FakeContext())

        assert resp["statusCode"] == 201
        plaintext_code = json.loads(resp["body"])["pairing_code"]

        insert_call = next(
            c for c in rds.execute_statement.call_args_list
            if "INSERT INTO devices" in c.kwargs.get("sql", "")
        )
        params = {p["name"]: p["value"]["stringValue"] for p in insert_call.kwargs["parameters"]}
        assert params["code"] != plaintext_code, "pairing code must not be stored as plaintext"
        assert len(params["code"]) == 64, "expected HMAC-SHA256 hex digest (64 chars)"
