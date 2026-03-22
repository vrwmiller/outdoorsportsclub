"""Tests for functions/members/me/handler.py

GET /v1/members/me — returns authenticated member's profile + current annual dues.
"""
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import (
    FAKE_MEMBER_ID,
    FAKE_SUB,
    FakeContext,
    member_jwt_event,
    load_member_handler,
)
from tests.helpers import make_member_rds, full_member_profile_row, club_settings_row

_MEMBER = {"member_id": FAKE_MEMBER_ID, "sub": FAKE_SUB, "training_level": 3}

_MOD_NAME = "member_me_handler"


@pytest.fixture()
def mod():
    m = load_member_handler("me")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", _MOD_NAME):
            del sys.modules[key]


class TestMemberMe:
    def test_success_returns_profile(self, mod):
        rds = make_member_rds({
            "members WHERE id": {"records": [full_member_profile_row()]},
            "club_settings": {"records": [[{"longValue": 10000}]]},
        })
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["member_num"] == "MBR-001"
        assert body["training_level"] == 3
        assert body["annual_dues_cents"] == 10000
        assert "service_hours" in body

    def test_success_nullable_fields_are_none(self, mod):
        row = full_member_profile_row(
            dues_paid_until=None, waiver_signed_at=None, mobile_phone=None
        )
        rds = make_member_rds({
            "members WHERE id": {"records": [row]},
            "club_settings": {"records": [[{"longValue": 5000}]]},
        })
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["dues_paid_until"] is None
        assert body["waiver_signed_at"] is None
        assert body["mobile_phone"] is None

    def test_auth_failure_returns_403(self, mod):
        with patch.object(mod, "authenticate_member", side_effect=PermissionError("denied")):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert resp["statusCode"] == 403

    def test_member_not_found_returns_403(self, mod):
        rds = make_member_rds({
            "members WHERE id": {"records": []},
            "club_settings": {"records": [[{"longValue": 5000}]]},
        })
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert resp["statusCode"] == 403

    def test_cors_headers_present(self, mod):
        rds = make_member_rds({
            "members WHERE id": {"records": [full_member_profile_row()]},
            "club_settings": {"records": [[{"longValue": 5000}]]},
        })
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert "Access-Control-Allow-Origin" in resp["headers"]

    def test_db_error_returns_500(self, mod):
        rds = MagicMock()
        rds.begin_transaction.return_value = {"transactionId": "tx-1"}
        rds.execute_statement.side_effect = RuntimeError("DB connection lost")
        rds.rollback_transaction.return_value = {}
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert resp["statusCode"] == 500

    def test_db_error_triggers_rollback(self, mod):
        rds = MagicMock()
        rds.begin_transaction.return_value = {"transactionId": "tx-1"}
        rds.execute_statement.side_effect = RuntimeError("DB connection lost")
        rds.rollback_transaction.return_value = {}
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            mod.handler(member_jwt_event(), FakeContext())

        rds.rollback_transaction.assert_called_once()

    def test_training_level_from_aurora_not_jwt(self, mod):
        # JWT/auth says level 1; Aurora row says level 5.
        # Body must reflect the Aurora-queried value (correctness invariant:
        # training_level is always re-queried from Aurora, never taken from JWT).
        member_level_1 = {"member_id": FAKE_MEMBER_ID, "sub": FAKE_SUB, "training_level": 1}
        row = full_member_profile_row(training_level=5)
        rds = make_member_rds({
            "members WHERE id": {"records": [row]},
            "club_settings": {"records": [[{"longValue": 10000}]]},
        })
        with patch.object(mod, "authenticate_member", return_value=member_level_1), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["training_level"] == 5  # Aurora value, not JWT value (1)

    def test_service_hours_double_value(self, mod):
        # Aurora may return service_hours as NUMERIC → doubleValue; handler must handle both.
        row = full_member_profile_row()
        row[2] = {"doubleValue": 2.5}
        rds = make_member_rds({
            "members WHERE id": {"records": [row]},
            "club_settings": {"records": [[{"longValue": 10000}]]},
        })
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["service_hours"] == "2.5"

    def test_annual_dues_cents_none_when_club_settings_empty(self, mod):
        rds = make_member_rds({
            "members WHERE id": {"records": [full_member_profile_row()]},
            "club_settings": {"records": []},
        })
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["annual_dues_cents"] is None

    def test_rls_gucs_set_with_correct_member_id_and_training_level(self, mod):
        # Both RLS GUCs must be set before querying members to ensure the DB
        # enforces row-level security with the correct identity.
        rds = make_member_rds({
            "members WHERE id": {"records": [full_member_profile_row()]},
            "club_settings": {"records": [[{"longValue": 10000}]]},
        })
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            mod.handler(member_jwt_event(), FakeContext())

        calls = rds.execute_statement.call_args_list
        mid_call = next(c for c in calls if "current_member_id" in c.kwargs.get("sql", ""))
        level_call = next(c for c in calls if "current_training_level" in c.kwargs.get("sql", ""))
        params_mid = {p["name"]: p["value"] for p in mid_call.kwargs["parameters"]}
        params_level = {p["name"]: p["value"] for p in level_call.kwargs["parameters"]}
        assert params_mid["mid"]["stringValue"] == FAKE_MEMBER_ID
        assert params_level["level"]["stringValue"] == str(_MEMBER["training_level"])
