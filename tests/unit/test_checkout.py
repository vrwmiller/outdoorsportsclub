"""Tests for functions/kiosk/checkout/handler.py

POST /v1/kiosk/check-out — clears the member's lane, logs the checkout,
and advances the wait list (with optional SNS notification).
"""
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import FakeContext, device_event, load_kiosk_handler
from tests.helpers import make_rds


@pytest.fixture()
def mod():
    m = load_kiosk_handler("checkout")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", "kiosk_checkout_handler"):
            del sys.modules[key]


def _happy_rds():
    """RDS mock for a successful checkout (no wait list to advance)."""
    return make_rds({
        "set_config": {},
        "FROM members WHERE member_num": {"records": [[{"stringValue": "member-id-1"}]]},
        "FROM lanes": {"records": [[{"stringValue": "lane-id-1"}]]},
        "UPDATE lanes": {"numberOfRecordsUpdated": 1},
        "INSERT INTO activity_logs": {"numberOfRecordsUpdated": 1},
        # _advance_wait_list: no one waiting
        "FROM wait_list": {"records": []},
    })


class TestCheckout:
    def test_happy_path_clears_lane(self, mod):
        sns = MagicMock()
        with patch("boto3.client", side_effect=lambda svc, **k: sns if svc == "sns" else _happy_rds()):
            resp = mod.handler(device_event({"member_num": "QR001"}), FakeContext())
        assert resp["statusCode"] == 200

    def test_missing_device_token_returns_403(self, mod):
        event = {"httpMethod": "POST", "headers": {}, "body": json.dumps({"member_num": "QR001"})}
        rds = MagicMock()
        rds.execute_statement.return_value = {"records": []}
        with patch("boto3.client", return_value=rds):
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

    def test_non_string_member_num_returns_400(self, mod):
        with patch("boto3.client", return_value=_happy_rds()):
            resp = mod.handler(device_event({"member_num": 12345}), FakeContext())
        assert resp["statusCode"] == 400

    def test_overlong_member_num_returns_400(self, mod):
        with patch("boto3.client", return_value=_happy_rds()):
            resp = mod.handler(device_event({"member_num": "A" * 65}), FakeContext())
        assert resp["statusCode"] == 400

    def test_member_not_checked_in_returns_404(self, mod):
        rds = make_rds({
            "set_config": {},
            "FROM members WHERE member_num": {"records": [[{"stringValue": "member-id-1"}]]},
            "FROM lanes": {"records": []},  # member not occupying a lane
        })
        sns = MagicMock()
        with patch("boto3.client", side_effect=lambda svc, **k: sns if svc == "sns" else rds):
            resp = mod.handler(device_event({"member_num": "QR001"}), FakeContext())
        assert resp["statusCode"] == 404

    def test_wait_list_advanced_with_sns_notification(self, mod):
        rds = make_rds({
            "set_config": {},
            "FROM members WHERE member_num": {"records": [[{"stringValue": "member-id-1"}]]},
            "FROM lanes": {"records": [[{"stringValue": "lane-id-1"}]]},
            "UPDATE lanes": {"numberOfRecordsUpdated": 1},
            "INSERT INTO activity_logs": {"numberOfRecordsUpdated": 1},
            # _advance_wait_list returns the next member
            "FROM wait_list": {"records": [[{"stringValue": "wl-id-1"}, {"stringValue": "member-id-2"}]]},
            "UPDATE wait_list": {"numberOfRecordsUpdated": 1},
            "FROM members WHERE id": {"records": [[{"stringValue": "+15555550100"}]]},
        })
        sns = MagicMock()
        with patch("boto3.client", side_effect=lambda svc, **k: sns if svc == "sns" else rds):
            resp = mod.handler(device_event({"member_num": "QR001"}), FakeContext())
        assert resp["statusCode"] == 200
        sns.publish.assert_called_once()

    def test_aws_failure_returns_500(self, mod):
        rds = MagicMock()
        rds.execute_statement.side_effect = Exception("timeout")
        rds.begin_transaction.return_value = {"transactionId": "tx-1"}
        rds.rollback_transaction.return_value = {}
        sns = MagicMock()
        with patch("boto3.client", side_effect=lambda svc, **k: sns if svc == "sns" else rds):
            resp = mod.handler(device_event({"member_num": "QR001"}), FakeContext())
        assert resp["statusCode"] == 500

    def test_cors_headers_present(self, mod):
        sns = MagicMock()
        with patch("boto3.client", side_effect=lambda svc, **k: sns if svc == "sns" else _happy_rds()):
            resp = mod.handler(device_event({"member_num": "QR001"}), FakeContext())
        assert "Access-Control-Allow-Origin" in resp["headers"]

    def test_sns_failure_after_commit_still_returns_200(self, mod):
        """SNS publish failure after DB commit must return 200 — checkout is committed."""
        rds = make_rds({
            "set_config": {},
            "FROM members WHERE member_num": {"records": [[{"stringValue": "member-id-1"}]]},
            "FROM lanes": {"records": [[{"stringValue": "lane-id-1"}]]},
            "UPDATE lanes": {"numberOfRecordsUpdated": 1},
            "INSERT INTO activity_logs": {"numberOfRecordsUpdated": 1},
            # _advance_wait_list returns a phone number so SNS is attempted
            "FROM wait_list": {"records": [[{"stringValue": "wl-id-1"}, {"stringValue": "member-id-2"}]]},
            "UPDATE wait_list": {"numberOfRecordsUpdated": 1},
            "FROM members WHERE id": {"records": [[{"stringValue": "+15555550100"}]]},
        })
        sns = MagicMock()
        sns.publish.side_effect = Exception("SNS unavailable")
        with patch("boto3.client", side_effect=lambda svc, **k: sns if svc == "sns" else rds):
            resp = mod.handler(device_event({"member_num": "QR001"}), FakeContext())
        assert resp["statusCode"] == 200
        sns.publish.assert_called_once()
