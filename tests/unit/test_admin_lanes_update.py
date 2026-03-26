"""Tests for functions/admin/lanes-update/handler.py

PATCH /v1/admin/lanes/{lane_id} — Level 4+ updates lane config or status.
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

_MOD_NAME = "admin_lanes_update_handler"

_LANE_ID = "eeeeeeee-ffff-0000-1111-222222222222"

_AVAILABLE_ROW = [[
    {"stringValue": _LANE_ID},
    {"longValue": 1},
    {"stringValue": "Available"},
]]


def _event(body, lane_id=_LANE_ID):
    return member_jwt_event(body, path_params={"lane_id": lane_id}, method="PATCH")


@pytest.fixture()
def mod():
    m = load_admin_handler("lanes-update")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", _MOD_NAME):
            del sys.modules[key]


class TestAdminLanesUpdate:
    def test_close_available_lane(self, mod):
        rds = make_member_rds({
            "FROM lanes WHERE id": {"records": [[
                {"stringValue": _LANE_ID},
                {"longValue": 1},
                {"stringValue": "Available"},
            ]]},
            "UPDATE lanes SET": {"records": [[
                {"stringValue": _LANE_ID},
                {"longValue": 1},
                {"stringValue": "Closed"},
            ]]},
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(_event({"status": "Closed"}), FakeContext())

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["status"] == "Closed"

    def test_close_occupied_lane_returns_409(self, mod):
        rds = make_member_rds({
            "FROM lanes WHERE id": {"records": [[
                {"stringValue": _LANE_ID},
                {"longValue": 1},
                {"stringValue": "Occupied"},
            ]]},
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(_event({"status": "Closed"}), FakeContext())

        assert resp["statusCode"] == 409

    def test_renumber_lane(self, mod):
        rds = make_member_rds({
            "FROM lanes WHERE id": {"records": [[
                {"stringValue": _LANE_ID},
                {"longValue": 1},
                {"stringValue": "Available"},
            ]]},
            "UPDATE lanes SET": {"records": [[
                {"stringValue": _LANE_ID},
                {"longValue": 5},
                {"stringValue": "Available"},
            ]]},
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(_event({"lane_number": 5}), FakeContext())

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["lane_number"] == 5

    def test_lane_not_found_returns_404(self, mod):
        rds = make_member_rds({
            "FROM lanes WHERE id": {"records": []},
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(_event({"status": "Closed"}), FakeContext())

        assert resp["statusCode"] == 404

    def test_invalid_status_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(_event({"status": "Occupied"}), FakeContext())

        assert resp["statusCode"] == 400

    def test_no_updatable_fields_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(_event({}), FakeContext())

        assert resp["statusCode"] == 400

    def test_level_3_returns_403(self, mod):
        low = {"member_id": FAKE_MEMBER_ID, "sub": FAKE_SUB, "training_level": 3}
        with patch.object(mod, "authenticate_member", return_value=low):
            resp = mod.handler(_event({"status": "Closed"}), FakeContext())

        assert resp["statusCode"] == 403

    def test_auth_failure_returns_403(self, mod):
        with patch.object(mod, "authenticate_member", side_effect=PermissionError("denied")):
            resp = mod.handler(_event({"status": "Closed"}), FakeContext())

        assert resp["statusCode"] == 403

    def test_invalid_lane_id_returns_400(self, mod):
        """Non-UUID lane_id path parameter must be rejected before any RDS call."""
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(_event({"status": "Closed"}, lane_id="not-a-uuid"), FakeContext())

        assert resp["statusCode"] == 400

    def test_lane_number_too_large_returns_400(self, mod):
        """lane_number > 32767 (SMALLINT max) must be rejected with 400."""
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(_event({"lane_number": 32768}), FakeContext())

        assert resp["statusCode"] == 400
