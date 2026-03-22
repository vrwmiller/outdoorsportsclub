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
