"""Tests for functions/admin/ranges-occupancy/handler.py

GET /v1/admin/ranges/occupancy — Level 4+ RSO view of all lanes across all ranges.
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

_MOD_NAME = "admin_ranges_occupancy_handler"


@pytest.fixture()
def mod():
    m = load_admin_handler("ranges-occupancy")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", _MOD_NAME):
            del sys.modules[key]


_RANGE_ROW = [{"stringValue": "range-1"}, {"stringValue": "Main Range"}, {"booleanValue": True}]
_LANE_ROW = [
    {"stringValue": "lane-1"},
    {"stringValue": "range-1"},
    {"longValue": 1},
    {"stringValue": "Available"},
    {"isNull": True},
    {"longValue": 0},
]


class TestAdminRangesOccupancy:
    def test_success_returns_ranges_with_lanes(self, mod):
        rds = make_member_rds({
            "FROM ranges ORDER BY": {"records": [_RANGE_ROW]},
            "FROM lanes ORDER BY": {"records": [_LANE_ROW]},
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["range_id"] == "range-1"
        assert len(body[0]["lanes"]) == 1
        assert body[0]["lanes"][0]["lane_id"] == "lane-1"

    def test_empty_ranges_returns_empty_list(self, mod):
        rds = make_member_rds({
            "FROM ranges ORDER BY": {"records": []},
            "FROM lanes ORDER BY": {"records": []},
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body == []

    def test_level_3_returns_403(self, mod):
        low_level = {"member_id": FAKE_MEMBER_ID, "sub": FAKE_SUB, "training_level": 3}
        with patch.object(mod, "authenticate_member", return_value=low_level):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert resp["statusCode"] == 403

    def test_auth_failure_returns_403(self, mod):
        with patch.object(mod, "authenticate_member", side_effect=PermissionError("denied")):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert resp["statusCode"] == 403

    def test_cors_headers_present(self, mod):
        rds = make_member_rds({
            "FROM ranges ORDER BY": {"records": []},
            "FROM lanes ORDER BY": {"records": []},
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert "Access-Control-Allow-Origin" in resp["headers"]
