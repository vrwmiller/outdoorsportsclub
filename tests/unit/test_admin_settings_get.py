"""Tests for functions/admin/settings-get/handler.py

GET /v1/admin/settings — Level 5+ returns current club_settings row.
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
from tests.helpers import make_member_rds, club_settings_row

_ADMIN = {"member_id": FAKE_MEMBER_ID, "sub": FAKE_SUB, "training_level": 5}

_MOD_NAME = "admin_settings_get_handler"


@pytest.fixture()
def mod():
    m = load_admin_handler("settings-get")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", _MOD_NAME):
            del sys.modules[key]


class TestAdminSettingsGet:
    def test_success_returns_settings(self, mod):
        rds = make_member_rds({
            "FROM club_settings LIMIT": {"records": [club_settings_row(annual_dues_cents=7500)]},
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["annual_dues_cents"] == 7500
        assert "updated_at" in body
        assert "updated_by_member_id" in body

    def test_level_4_returns_403(self, mod):
        low = {"member_id": FAKE_MEMBER_ID, "sub": FAKE_SUB, "training_level": 4}
        with patch.object(mod, "authenticate_member", return_value=low):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert resp["statusCode"] == 403

    def test_auth_failure_returns_403(self, mod):
        with patch.object(mod, "authenticate_member", side_effect=PermissionError("denied")):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert resp["statusCode"] == 403

    def test_cors_headers_present(self, mod):
        rds = make_member_rds({
            "FROM club_settings LIMIT": {"records": [club_settings_row()]},
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert "Access-Control-Allow-Origin" in resp["headers"]
