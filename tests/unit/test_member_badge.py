"""Tests for functions/members/me-badge/handler.py

GET /v1/members/me/badge — returns member_num for QR code display.
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
    load_member_handler,
)
from tests.helpers import make_member_rds

_MEMBER = {"member_id": FAKE_MEMBER_ID, "sub": FAKE_SUB, "training_level": 3}

_MOD_NAME = "member_me_badge_handler"


@pytest.fixture()
def mod():
    m = load_member_handler("me-badge")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", _MOD_NAME):
            del sys.modules[key]


class TestMemberBadge:
    def test_success_returns_member_num(self, mod):
        rds = make_member_rds({
            "member_num FROM members": {"records": [[{"stringValue": "MBR-042"}]]},
        })
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["member_num"] == "MBR-042"

    def test_member_not_found_returns_403(self, mod):
        rds = make_member_rds({
            "member_num FROM members": {"records": []},
        })
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert resp["statusCode"] == 403

    def test_auth_failure_returns_403(self, mod):
        with patch.object(mod, "authenticate_member", side_effect=PermissionError("denied")):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert resp["statusCode"] == 403

    def test_cors_headers_present(self, mod):
        rds = make_member_rds({
            "member_num FROM members": {"records": [[{"stringValue": "MBR-001"}]]},
        })
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert "Access-Control-Allow-Origin" in resp["headers"]
