"""Tests for functions/kiosk/range-lanes/handler.py

GET /v1/kiosk/range/lanes — returns current lane occupancy for the device's range.
"""
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import (
    FakeContext,
    active_device_row,
    device_event,
    load_kiosk_handler,
)


@pytest.fixture()
def mod():
    m = load_kiosk_handler("range-lanes")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", "kiosk_range-lanes_handler"):
            del sys.modules[key]


# ---------------------------------------------------------------------------
# RDS mock helpers
# ---------------------------------------------------------------------------

def _rds(*, range_found=True, is_open=True, lanes=None):
    """Build a mock rds-data client for the range-lanes handler."""
    rds = MagicMock()

    # begin_transaction
    rds.begin_transaction.return_value = {"transactionId": "tx-1"}

    # Device auth query
    rds.execute_statement.side_effect = _make_execute_side_effect(
        range_found=range_found, is_open=is_open, lanes=lanes
    )
    return rds


def _make_execute_side_effect(range_found, is_open, lanes):
    call_count = [0]
    default_lanes = lanes if lanes is not None else [
        [
            {"stringValue": "lane-id-1"},
            {"longValue": 1},
            {"stringValue": "Available"},
            {"isNull": True},
            {"longValue": 0},
            {"isNull": True},
        ]
    ]

    def side_effect(**kwargs):
        call_count[0] += 1
        sql = kwargs.get("sql", "")
        if "set_config" in sql:
            return {}
        if "SELECT name, is_open FROM ranges" in sql:
            if not range_found:
                return {"records": []}
            return {"records": [[{"stringValue": "Rifle Range"}, {"booleanValue": is_open}]]}
        if "FROM lanes" in sql:
            return {"records": default_lanes}
        # device auth
        if "SELECT id, range_id, status FROM devices" in sql:
            return {"records": [active_device_row()]}
        return {"records": []}

    return side_effect


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRangeLanes:
    def test_happy_path_returns_lanes(self, mod):
        auth_rds = MagicMock()
        auth_rds.execute_statement.return_value = {"records": [active_device_row()]}

        call_seq = [0]

        def boto_factory(svc, **kw):
            call_seq[0] += 1
            if svc == "rds-data":
                # First call is from _auth.authenticate_device, rest from handler
                if call_seq[0] == 1:
                    return auth_rds
                return _rds()
            return MagicMock()

        with patch("boto3.client", side_effect=boto_factory):
            resp = mod.handler(device_event(), FakeContext())

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert "lanes" in body
        assert "range_id" in body or "name" in body
        # SEC-29: internal member UUID must never appear in the lane payload
        for lane in body["lanes"]:
            assert "current_member_id" not in lane

    def test_missing_device_token_returns_403(self, mod):
        event = {"httpMethod": "GET", "headers": {}, "body": None}
        rds_auth = MagicMock()
        rds_auth.execute_statement.return_value = {"records": []}
        with patch("boto3.client", return_value=rds_auth):
            resp = mod.handler(event, FakeContext())
        assert resp["statusCode"] == 403

    def test_invalid_device_token_returns_403(self, mod):
        event = {"httpMethod": "GET", "headers": {"x-device-token": "wrong"}, "body": None}
        rds_auth = MagicMock()
        rds_auth.execute_statement.return_value = {"records": []}
        with patch("boto3.client", return_value=rds_auth):
            resp = mod.handler(event, FakeContext())
        assert resp["statusCode"] == 403

    def test_revoked_device_returns_403(self, mod):
        event = device_event()
        rds_auth = MagicMock()
        rds_auth.execute_statement.return_value = {
            "records": [
                [{"stringValue": "d1"}, {"stringValue": "r1"}, {"stringValue": "Revoked"}]
            ]
        }
        with patch("boto3.client", return_value=rds_auth):
            resp = mod.handler(event, FakeContext())
        assert resp["statusCode"] == 403

    def test_aws_failure_returns_500(self, mod):
        rds = MagicMock()
        rds.execute_statement.side_effect = Exception("connection timeout")
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(device_event(), FakeContext())
        assert resp["statusCode"] == 500

    def test_cors_headers_present(self, mod):
        rds_auth = MagicMock()
        rds_auth.execute_statement.return_value = {"records": []}
        with patch("boto3.client", return_value=rds_auth):
            resp = mod.handler(device_event(), FakeContext())
        assert "Access-Control-Allow-Origin" in resp["headers"]
