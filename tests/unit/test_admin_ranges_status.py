"""Tests for functions/admin/ranges-status/handler.py

PATCH /v1/admin/ranges/{range_id}/status — Level 4+ sets is_open flag.
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

_ADMIN = {"member_id": FAKE_MEMBER_ID, "sub": FAKE_SUB, "training_level": 4}

_MOD_NAME = "admin_ranges_status_handler"

_RANGE_ID = "range-id-1"


@pytest.fixture()
def mod():
    m = load_admin_handler("ranges-status")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", _MOD_NAME):
            del sys.modules[key]


def _event(is_open: bool):
    return member_jwt_event(
        {"is_open": is_open},
        path_params={"range_id": _RANGE_ID},
        method="PATCH",
    )


class TestAdminRangesStatus:
    def test_close_range(self, mod):
        rds = make_member_rds({
            "UPDATE ranges SET is_open": {"records": [[
                {"stringValue": _RANGE_ID},
                {"booleanValue": False},
            ]]},
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(_event(False), FakeContext())

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["is_open"] is False
        assert body["range_id"] == _RANGE_ID

    def test_open_range(self, mod):
        rds = make_member_rds({
            "UPDATE ranges SET is_open": {"records": [[
                {"stringValue": _RANGE_ID},
                {"booleanValue": True},
            ]]},
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(_event(True), FakeContext())

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["is_open"] is True

    def test_range_not_found_returns_404(self, mod):
        rds = make_member_rds({
            "UPDATE ranges SET is_open": {"records": []},
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(_event(False), FakeContext())

        assert resp["statusCode"] == 404

    def test_missing_is_open_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(
                member_jwt_event({}, path_params={"range_id": _RANGE_ID}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_non_bool_is_open_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(
                member_jwt_event(
                    {"is_open": "yes"}, path_params={"range_id": _RANGE_ID}, method="PATCH"
                ),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_level_3_returns_403(self, mod):
        low = {"member_id": FAKE_MEMBER_ID, "sub": FAKE_SUB, "training_level": 3}
        with patch.object(mod, "authenticate_member", return_value=low):
            resp = mod.handler(_event(False), FakeContext())

        assert resp["statusCode"] == 403

    def test_auth_failure_returns_403(self, mod):
        with patch.object(mod, "authenticate_member", side_effect=PermissionError("denied")):
            resp = mod.handler(_event(False), FakeContext())

        assert resp["statusCode"] == 403
