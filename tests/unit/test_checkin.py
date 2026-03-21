"""Tests for functions/kiosk/checkin/handler.py

POST /v1/kiosk/check-in — validates member, dues, training level,
and either assigns a lane or adds to the wait list.
"""
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import FakeContext, device_event, load_kiosk_handler
from tests.helpers import make_rds, member_row


@pytest.fixture()
def mod():
    m = load_kiosk_handler("checkin")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", "kiosk_checkin_handler"):
            del sys.modules[key]


def _member_range_policy():
    """Common SQL responses for member/range/policy lookups."""
    return {
        "set_config": {"records": []},
        "FROM members WHERE member_num": {
            "records": [member_row(training_level=3, dues_paid_until="2030-01-01")]
        },
        "FROM ranges WHERE id": {
            "records": [[{"booleanValue": True}, {"longValue": 2}]]
        },
        "FROM training_level_policies": {
            "records": [[{"longValue": 2}]]
        },
    }


def _happy_rds():
    """RDS mock for a successful lane assignment.

    Uses specific SQL fragments to distinguish the three lane queries:
    - "FROM wait_list WHERE member_id" : existing-entry check (step 5)
    - "SELECT id, lane_number"         : available lanes SELECT (step 6)
    - "AND status = 'Occupied'"        : occupied lanes SELECT (step 8a)
    - "SET status = 'Occupied'"        : UPDATE lane to Occupied (step 8c)
    """
    return make_rds({
        **_member_range_policy(),
        "FROM wait_list WHERE member_id": {"records": []},
        "SELECT id, lane_number": {
            "records": [[{"stringValue": "lane-id-1"}, {"longValue": 1}]]
        },
        "AND status = 'Occupied'": {"records": []},
        "SET status = 'Occupied'": {"numberOfRecordsUpdated": 1},
        "INSERT INTO activity_logs": {"numberOfRecordsUpdated": 1},
    })


class TestCheckin:
    def test_happy_path_assigns_lane(self, mod):
        with patch("boto3.client", return_value=_happy_rds()):
            resp = mod.handler(
                device_event({"member_num": "QR001", "guest_count": 0}),
                FakeContext(),
            )
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert "lane_number" in body

    def test_happy_path_waitlisted_when_range_full(self, mod):
        rds = make_rds({
            **_member_range_policy(),
            "FROM wait_list WHERE member_id": {"records": []},
            "SELECT id, lane_number": {"records": []},  # no available lanes
            "COALESCE(MAX(position), 0)": {"records": [[{"longValue": 1}]]},
            "INSERT INTO wait_list": {"numberOfRecordsUpdated": 1},
        })
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(
                device_event({"member_num": "QR001", "guest_count": 0}),
                FakeContext(),
            )
        assert resp["statusCode"] == 202
        body = json.loads(resp["body"])
        assert "wait_position" in body

    def test_missing_device_token_returns_403(self, mod):
        event = {"httpMethod": "POST", "headers": {}, "body": json.dumps({"member_num": "QR001"})}
        with patch("boto3.client", return_value=MagicMock(execute_statement=MagicMock(return_value={"records": []}))):
            resp = mod.handler(event, FakeContext())
        assert resp["statusCode"] == 403

    def test_revoked_device_returns_403(self, mod):
        rds = MagicMock()
        rds.execute_statement.return_value = {
            "records": [[{"stringValue": "d1"}, {"stringValue": "r1"}, {"stringValue": "Revoked"}]]
        }
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(device_event({"member_num": "QR001"}), FakeContext())
        assert resp["statusCode"] == 403

    def test_missing_member_num_returns_400(self, mod):
        with patch("boto3.client", return_value=_happy_rds()):
            resp = mod.handler(device_event({}), FakeContext())
        assert resp["statusCode"] == 400

    def test_invalid_guest_count_returns_400(self, mod):
        with patch("boto3.client", return_value=_happy_rds()):
            resp = mod.handler(device_event({"member_num": "QR001", "guest_count": 5}), FakeContext())
        assert resp["statusCode"] == 400

    def test_range_closed_returns_403(self, mod):
        rds = make_rds({
            "set_config": {},
            "FROM members WHERE member_num": {
                "records": [member_row(training_level=3, dues_paid_until="2030-01-01")]
            },
            "FROM ranges WHERE id": {
                "records": [[{"booleanValue": False}, {"longValue": 2}]]  # is_open=False
            },
        })
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(device_event({"member_num": "QR001"}), FakeContext())
        assert resp["statusCode"] == 403

    def test_insufficient_training_level_returns_403(self, mod):
        rds = make_rds({
            "set_config": {},
            "FROM members WHERE member_num": {
                "records": [member_row(training_level=1, dues_paid_until="2030-01-01")]
            },
            "FROM ranges WHERE id": {
                "records": [[{"booleanValue": True}, {"longValue": 3}]]  # requires level 3
            },
        })
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(device_event({"member_num": "QR001"}), FakeContext())
        assert resp["statusCode"] == 403

    def test_dues_expired_returns_403(self, mod):
        rds = make_rds({
            "set_config": {},
            "FROM members WHERE member_num": {
                "records": [member_row(training_level=3, dues_paid_until="2020-01-01")]
            },
            "FROM ranges WHERE id": {
                "records": [[{"booleanValue": True}, {"longValue": 2}]]
            },
        })
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(device_event({"member_num": "QR001"}), FakeContext())
        assert resp["statusCode"] == 403

    def test_aws_failure_returns_500(self, mod):
        rds = MagicMock()
        rds.execute_statement.side_effect = Exception("DB unavailable")
        rds.begin_transaction.return_value = {"transactionId": "tx-1"}
        rds.rollback_transaction.return_value = {}
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(device_event({"member_num": "QR001"}), FakeContext())
        assert resp["statusCode"] == 500

    def test_cors_headers_present(self, mod):
        with patch("boto3.client", return_value=_happy_rds()):
            resp = mod.handler(device_event({"member_num": "QR001"}), FakeContext())
        assert "Access-Control-Allow-Origin" in resp["headers"]
