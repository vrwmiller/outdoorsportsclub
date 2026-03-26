"""Tests for functions/admin/lanes-create/handler.py

POST /v1/admin/lanes — Level 4+ creates a new lane for a range.
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

_MOD_NAME = "admin_lanes_create_handler"

_RANGE_ID = "11111111-2222-3333-4444-555555555555"

_INSERT_ROW = [[
    {"stringValue": "lane-new-1"},
    {"stringValue": _RANGE_ID},
    {"longValue": 3},
    {"stringValue": "Available"},
]]


@pytest.fixture()
def mod():
    m = load_admin_handler("lanes-create")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", _MOD_NAME):
            del sys.modules[key]


class TestAdminLanesCreate:
    def test_success_returns_201(self, mod):
        rds = make_member_rds({
            "INSERT INTO lanes": {"records": _INSERT_ROW},
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event({"range_id": _RANGE_ID, "lane_number": 3}, method="POST"),
                FakeContext(),
            )

        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert body["lane_id"] == "lane-new-1"
        assert body["lane_number"] == 3
        assert body["status"] == "Available"

    def test_duplicate_lane_returns_409(self, mod):
        # Only the INSERT should raise; set_config calls must succeed.
        rds = make_member_rds({})
        orig = rds.execute_statement.side_effect

        def _insert_fails(**kwargs):
            if "INSERT INTO lanes" in kwargs.get("sql", ""):
                raise Exception("duplicate key value violates unique constraint uq_lanes_range_lane")
            return orig(**kwargs)

        rds.execute_statement.side_effect = _insert_fails
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event({"range_id": _RANGE_ID, "lane_number": 1}, method="POST"),
                FakeContext(),
            )

        assert resp["statusCode"] == 409

    def test_missing_range_id_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(
                member_jwt_event({"lane_number": 1}, method="POST"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_missing_lane_number_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(
                member_jwt_event({"range_id": _RANGE_ID}, method="POST"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_zero_lane_number_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(
                member_jwt_event({"range_id": _RANGE_ID, "lane_number": 0}, method="POST"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_level_3_returns_403(self, mod):
        low = {"member_id": FAKE_MEMBER_ID, "sub": FAKE_SUB, "training_level": 3}
        with patch.object(mod, "authenticate_member", return_value=low):
            resp = mod.handler(
                member_jwt_event({"range_id": _RANGE_ID, "lane_number": 1}, method="POST"),
                FakeContext(),
            )

        assert resp["statusCode"] == 403

    def test_auth_failure_returns_403(self, mod):
        with patch.object(mod, "authenticate_member", side_effect=PermissionError("denied")):
            resp = mod.handler(
                member_jwt_event({"range_id": _RANGE_ID, "lane_number": 1}, method="POST"),
                FakeContext(),
            )

        assert resp["statusCode"] == 403

    def test_non_uuid_range_id_returns_400(self, mod):
        """Non-UUID string range_id must be rejected before any RDS call."""
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(
                member_jwt_event({"range_id": "not-a-uuid", "lane_number": 1}, method="POST"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_non_string_range_id_returns_400(self, mod):
        """Integer range_id must be rejected — only strings are accepted."""
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(
                member_jwt_event({"range_id": 123, "lane_number": 1}, method="POST"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_boolean_lane_number_returns_400(self, mod):
        """Boolean lane_number must be rejected (bool is a subclass of int in Python)."""
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(
                member_jwt_event({"range_id": _RANGE_ID, "lane_number": True}, method="POST"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_lane_number_too_large_returns_400(self, mod):
        """lane_number > 32767 (SMALLINT max) must be rejected with 400."""
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(
                member_jwt_event({"range_id": _RANGE_ID, "lane_number": 32768}, method="POST"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_nonexistent_range_id_returns_400(self, mod):
        """FK violation on a nonexistent range_id must return 400, not 500."""
        rds = make_member_rds({})
        orig = rds.execute_statement.side_effect

        def _fk_fails(**kwargs):
            if "INSERT INTO lanes" in kwargs.get("sql", ""):
                raise Exception('violates foreign key constraint "fk_lanes_range_id"')
            return orig(**kwargs)

        rds.execute_statement.side_effect = _fk_fails
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event({"range_id": _RANGE_ID, "lane_number": 1}, method="POST"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400
