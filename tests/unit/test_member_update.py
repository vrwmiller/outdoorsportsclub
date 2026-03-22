"""Tests for functions/members/me-update/handler.py

PATCH /v1/members/me — updates home_phone and/or mobile_phone.
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

_MOD_NAME = "member_me_update_handler"

_UPDATE_ROW = [[{"stringValue": "+15559990000"}, {"stringValue": "+15551234567"}]]


@pytest.fixture()
def mod():
    m = load_member_handler("me-update")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", _MOD_NAME):
            del sys.modules[key]


class TestMemberUpdate:
    def test_update_mobile_phone(self, mod):
        rds = make_member_rds({
            "RETURNING home_phone": {"records": _UPDATE_ROW},
        })
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event({"mobile_phone": "+15551234567"}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert "mobile_phone" in body

    def test_update_home_phone(self, mod):
        rds = make_member_rds({
            "RETURNING home_phone": {"records": _UPDATE_ROW},
        })
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event({"home_phone": "+15559990000"}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert "home_phone" in body

    def test_set_phone_to_null(self, mod):
        rds = make_member_rds({
            "RETURNING home_phone": {"records": [[{"isNull": True}, {"isNull": True}]]},
        })
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event({"mobile_phone": None}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 200

    def test_invalid_e164_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_MEMBER):
            resp = mod.handler(
                member_jwt_event({"mobile_phone": "not-a-number"}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_no_updatable_fields_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_MEMBER):
            resp = mod.handler(
                member_jwt_event({"email": "hacker@example.com"}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_empty_body_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_MEMBER):
            resp = mod.handler(member_jwt_event({}, method="PATCH"), FakeContext())

        assert resp["statusCode"] == 400

    def test_auth_failure_returns_403(self, mod):
        with patch.object(mod, "authenticate_member", side_effect=PermissionError("denied")):
            resp = mod.handler(
                member_jwt_event({"mobile_phone": "+15551234567"}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 403

    def test_cors_headers_present(self, mod):
        rds = make_member_rds({
            "RETURNING home_phone": {"records": _UPDATE_ROW},
        })
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event({"mobile_phone": "+15551234567"}, method="PATCH"),
                FakeContext(),
            )

        assert "Access-Control-Allow-Origin" in resp["headers"]
