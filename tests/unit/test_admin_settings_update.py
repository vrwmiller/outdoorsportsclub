"""Tests for functions/admin/settings-update/handler.py

PATCH /v1/admin/settings — Level 5+ updates annual_dues_cents.
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

_ADMIN = {"member_id": FAKE_MEMBER_ID, "sub": FAKE_SUB, "training_level": 5}

_MOD_NAME = "admin_settings_update_handler"

_SETTINGS_RETURN = [[{"longValue": 12000}, {"stringValue": "2025-01-01T00:00:00Z"}]]


@pytest.fixture()
def mod():
    m = load_admin_handler("settings-update")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", _MOD_NAME):
            del sys.modules[key]


class TestAdminSettingsUpdate:
    def test_success_updates_dues(self, mod):
        rds = make_member_rds({
            "UPDATE club_settings": {"records": _SETTINGS_RETURN},
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event({"annual_dues_cents": 12000}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["annual_dues_cents"] == 12000
        assert "updated_at" in body

    def test_zero_dues_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(
                member_jwt_event({"annual_dues_cents": 0}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_negative_dues_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(
                member_jwt_event({"annual_dues_cents": -100}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_missing_field_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(
                member_jwt_event({}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_level_4_returns_403(self, mod):
        low = {"member_id": FAKE_MEMBER_ID, "sub": FAKE_SUB, "training_level": 4}
        with patch.object(mod, "authenticate_member", return_value=low):
            resp = mod.handler(
                member_jwt_event({"annual_dues_cents": 5000}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 403

    def test_auth_failure_returns_403(self, mod):
        with patch.object(mod, "authenticate_member", side_effect=PermissionError("denied")):
            resp = mod.handler(
                member_jwt_event({"annual_dues_cents": 5000}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 403

    def test_dues_above_max_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(
                member_jwt_event({"annual_dues_cents": 100_000}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400
        assert "exceeds maximum" in json.loads(resp["body"])["error"]

    def test_dues_at_max_succeeds(self, mod):
        rds = make_member_rds({
            "UPDATE club_settings": {"records": [[{"longValue": 99999}, {"stringValue": "2025-01-01T00:00:00Z"}]]},
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event({"annual_dues_cents": 99_999}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 200

    def test_null_body_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            event = member_jwt_event({"annual_dues_cents": 5000}, method="PATCH")
            event["body"] = "null"
            resp = mod.handler(event, FakeContext())

        assert resp["statusCode"] == 400
        assert "JSON object" in json.loads(resp["body"])["error"]

    def test_array_body_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            event = member_jwt_event({"annual_dues_cents": 5000}, method="PATCH")
            event["body"] = "[]"
            resp = mod.handler(event, FakeContext())

        assert resp["statusCode"] == 400
        assert "JSON object" in json.loads(resp["body"])["error"]

    def test_invalid_json_body_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            event = member_jwt_event({"annual_dues_cents": 5000}, method="PATCH")
            event["body"] = "{"
            resp = mod.handler(event, FakeContext())

        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"] == "Invalid JSON body"

    def test_audit_insert_and_prev_select_on_success(self, mod):
        rds = make_member_rds({
            "SELECT annual_dues_cents FROM club_settings": {
                "records": [[{"longValue": 10000}]]
            },
            "UPDATE club_settings": {
                "records": [[{"longValue": 12000}, {"stringValue": "2025-01-01T00:00:00Z"}]]
            },
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event({"annual_dues_cents": 12000}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 200
        calls = [c.kwargs.get("sql", c.args[0] if c.args else "") for c in rds.execute_statement.call_args_list]
        assert any("SELECT annual_dues_cents" in s for s in calls), "prev SELECT not executed"
        assert any("Settings-Change" in s for s in calls), "audit INSERT not executed"

    def test_boolean_true_returns_400(self, mod):
        # bool is a subclass of int; True must be rejected, not treated as 1 cent
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(
                member_jwt_event({"annual_dues_cents": True}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_boolean_false_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(
                member_jwt_event({"annual_dues_cents": False}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_cors_headers_present(self, mod):
        rds = make_member_rds({
            "UPDATE club_settings": {"records": _SETTINGS_RETURN},
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event({"annual_dues_cents": 5000}, method="PATCH"),
                FakeContext(),
            )

        assert "Access-Control-Allow-Origin" in resp["headers"]
