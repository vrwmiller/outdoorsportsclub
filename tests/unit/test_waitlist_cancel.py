"""Tests for functions/kiosk/waitlist-cancel/handler.py

DELETE /v1/kiosk/wait-list/{entry_id} — cancels a member's active wait-list entry
and recalculates positions for remaining Waiting entries.
"""
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import FakeContext, device_event, load_kiosk_handler
from tests.helpers import make_rds

FAKE_ENTRY_ID = "entry-id-1"
FAKE_MEMBER_ID = "member-id-1"


@pytest.fixture()
def mod():
    m = load_kiosk_handler("waitlist-cancel")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", "kiosk_waitlist-cancel_handler"):
            del sys.modules[key]


def _cancel_event(body: dict | None = None, entry_id: str = FAKE_ENTRY_ID):
    b = {"member_num": "M001"} if body is None else body
    evt = device_event(b)
    evt["pathParameters"] = {"entry_id": entry_id}
    return evt


def _rds_happy():
    return make_rds({
        "set_config": {"records": []},
        "FROM members WHERE member_num": {"records": [[{"stringValue": FAKE_MEMBER_ID}]]},
        "FROM wait_list": {"records": [
            [{"stringValue": FAKE_ENTRY_ID}, {"longValue": 2}]
        ]},
        "UPDATE wait_list SET status = 'Cancelled'": {"numberOfRecordsUpdated": 1},
        "UPDATE wait_list SET position = position - 1": {"numberOfRecordsUpdated": 1},
    })


class TestWaitlistCancel:
    def test_happy_path_cancels_entry(self, mod):
        rds = _rds_happy()
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(_cancel_event(), FakeContext())
        assert resp["statusCode"] == 200
        assert "cancelled" in json.loads(resp["body"])["message"].lower()

    def test_missing_device_token_returns_403(self, mod):
        event = {
            "httpMethod": "DELETE",
            "headers": {},
            "body": json.dumps({"member_num": "M001"}),
            "pathParameters": {"entry_id": FAKE_ENTRY_ID},
        }
        rds = MagicMock()
        rds.execute_statement.return_value = {"records": []}
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(event, FakeContext())
        assert resp["statusCode"] == 403

    def test_missing_entry_id_returns_400(self, mod):
        evt = device_event({"member_num": "M001"})
        evt["pathParameters"] = {}
        rds = make_rds({})  # auto-injects device auth
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(evt, FakeContext())
        assert resp["statusCode"] == 400

    def test_missing_member_num_returns_400(self, mod):
        rds = make_rds({})  # ValueError raised after device auth
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(_cancel_event(body={}), FakeContext())
        assert resp["statusCode"] == 400

    def test_non_string_member_num_returns_400(self, mod):
        rds = make_rds({})  # ValueError raised before any DB query
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(_cancel_event(body={"member_num": 12345}), FakeContext())
        assert resp["statusCode"] == 400

    def test_overlong_member_num_returns_400(self, mod):
        rds = make_rds({})  # ValueError raised before any DB query
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(_cancel_event(body={"member_num": "A" * 65}), FakeContext())
        assert resp["statusCode"] == 400

    def test_unknown_member_returns_404(self, mod):
        rds = make_rds({
            "set_config": {"records": []},
            "FROM members WHERE member_num": {"records": []},
        })
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(_cancel_event(body={"member_num": "UNKNOWN"}), FakeContext())
        assert resp["statusCode"] == 404

    def test_entry_not_found_returns_404(self, mod):
        # wait_list lookup returns no rows (entry belongs to different member/range,
        # or already Cancelled/Called)
        rds = make_rds({
            "set_config": {"records": []},
            "FROM members WHERE member_num": {"records": [[{"stringValue": FAKE_MEMBER_ID}]]},
            "FROM wait_list": {"records": []},
        })
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(_cancel_event(), FakeContext())
        assert resp["statusCode"] == 404

    def test_aws_failure_returns_500(self, mod):
        rds = MagicMock()
        rds.execute_statement.side_effect = Exception("DB offline")
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(_cancel_event(), FakeContext())
        assert resp["statusCode"] == 500

    def test_cors_headers_present(self, mod):
        rds = MagicMock()
        rds.execute_statement.return_value = {"records": []}
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(_cancel_event(), FakeContext())
        assert "Access-Control-Allow-Origin" in resp["headers"]
