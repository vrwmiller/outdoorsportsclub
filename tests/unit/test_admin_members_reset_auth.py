"""Tests for functions/admin/members-reset-auth/handler.py

PATCH /v1/admin/members/reset-auth — Level 6 clears social identity link.
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
    load_admin_handler,
)
from tests.helpers import make_member_rds

_WEBMASTER = {"member_id": FAKE_MEMBER_ID, "sub": FAKE_SUB, "training_level": 6}

_MOD_NAME = "admin_members_reset_auth_handler"

_TARGET_ID = "cccccccc-dddd-eeee-ffff-000000000003"

_MEMBER_ROW_WITH_IDP = [[
    {"stringValue": _TARGET_ID},
    {"stringValue": "target@example.com"},
    {"stringValue": "google_abc123"},
]]

_MEMBER_ROW_NO_IDP = [[
    {"stringValue": _TARGET_ID},
    {"stringValue": "target@example.com"},
    {"isNull": True},
]]


@pytest.fixture()
def mod():
    m = load_admin_handler("members-reset-auth")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", _MOD_NAME):
            del sys.modules[key]


class TestAdminMembersResetAuth:
    def test_success_with_idp_linked(self, mod):
        rds = make_member_rds({
            "FROM members WHERE id = :tid": {"records": _MEMBER_ROW_WITH_IDP},
            "social_provider_id = NULL": {"numberOfRecordsUpdated": 1},
        })
        cognito_mock = MagicMock()
        def _boto(svc, **kw):
            if svc == "cognito-idp":
                return cognito_mock
            return rds
        with patch.object(mod, "authenticate_member", return_value=_WEBMASTER), \
             patch("boto3.client", side_effect=_boto):
            resp = mod.handler(
                member_jwt_event({"member_id": _TARGET_ID}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 200

    def test_success_when_no_idp_linked(self, mod):
        """Handler should succeed gracefully even if social_provider_id is already NULL."""
        rds = make_member_rds({
            "FROM members WHERE id = :tid": {"records": _MEMBER_ROW_NO_IDP},
        })
        with patch.object(mod, "authenticate_member", return_value=_WEBMASTER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event({"member_id": _TARGET_ID}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 200

    def test_target_not_found_returns_404(self, mod):
        rds = make_member_rds({
            "FROM members WHERE id = :tid": {"records": []},
        })
        with patch.object(mod, "authenticate_member", return_value=_WEBMASTER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event({"member_id": _TARGET_ID}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 404

    def test_missing_member_id_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_WEBMASTER):
            resp = mod.handler(
                member_jwt_event({}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_level_5_actor_returns_403(self, mod):
        low = {"member_id": FAKE_MEMBER_ID, "sub": FAKE_SUB, "training_level": 5}
        with patch.object(mod, "authenticate_member", return_value=low):
            resp = mod.handler(
                member_jwt_event({"member_id": _TARGET_ID}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 403

    def test_cognito_error_still_returns_200(self, mod):
        """DB is committed before Cognito is called; any Cognito failure must not produce 500."""
        rds = make_member_rds({
            "FROM members WHERE id = :tid": {"records": _MEMBER_ROW_WITH_IDP},
            "social_provider_id = NULL": {"numberOfRecordsUpdated": 1},
        })
        cognito_mock = MagicMock()
        cognito_mock.admin_user_global_sign_out.side_effect = Exception("network error")
        def _boto(svc, **kw):
            if svc == "cognito-idp":
                return cognito_mock
            return rds
        with patch.object(mod, "authenticate_member", return_value=_WEBMASTER), \
             patch("boto3.client", side_effect=_boto):
            resp = mod.handler(
                member_jwt_event({"member_id": _TARGET_ID}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 200

    def test_auth_failure_returns_403(self, mod):
        with patch.object(mod, "authenticate_member", side_effect=PermissionError("denied")):
            resp = mod.handler(
                member_jwt_event({"member_id": _TARGET_ID}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 403
