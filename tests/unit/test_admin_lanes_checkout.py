"""Tests for functions/admin/lanes-checkout/handler.py

POST /v1/admin/lanes/{lane_id}/checkout — Level 4+ force-checks out a lane.
Clears lane, writes audit log, advances wait list, optionally sends SNS SMS.
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

_ADMIN = {"member_id": FAKE_MEMBER_ID, "sub": FAKE_SUB, "training_level": 4}

_MOD_NAME = "admin_lanes_checkout_handler"

_LANE_ID = "lane-id-1"
_OCCUPANT_ID = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"

_OCCUPIED_LANE = [[
    {"stringValue": _LANE_ID},
    {"stringValue": "range-id-1"},
    {"stringValue": "Occupied"},
    {"stringValue": _OCCUPANT_ID},
]]

_AVAILABLE_LANE = [[
    {"stringValue": _LANE_ID},
    {"stringValue": "range-id-1"},
    {"stringValue": "Available"},
    {"isNull": True},
]]


def _event(lane_id=_LANE_ID):
    return member_jwt_event(None, path_params={"lane_id": lane_id}, method="POST")


@pytest.fixture()
def mod():
    m = load_admin_handler("lanes-checkout")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", _MOD_NAME):
            del sys.modules[key]


class TestAdminLanesCheckout:
    def test_success_no_waitlist(self, mod):
        rds = make_member_rds({
            "FROM lanes WHERE id": {"records": _OCCUPIED_LANE},
            "SET status = 'Available'": {"numberOfRecordsUpdated": 1},
            "Range-Checkout": {"numberOfRecordsUpdated": 1},
            "UPDATE wait_list": {"records": []},  # no one waiting
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(_event(), FakeContext())

        assert resp["statusCode"] == 200

    def test_success_advances_waitlist_and_sends_sns(self, mod):
        rds = make_member_rds({
            "FROM lanes WHERE id": {"records": _OCCUPIED_LANE},
            "SET status = 'Available'": {"numberOfRecordsUpdated": 1},
            "Range-Checkout": {"numberOfRecordsUpdated": 1},
            "UPDATE wait_list": {"records": [[{"stringValue": "wl-id-1"}]]},
            "JOIN wait_list wl": {"records": [[{"stringValue": "+15555550100"}]]},
        })
        sns_mock = MagicMock()
        def _boto(svc, **kw):
            if svc == "sns":
                return sns_mock
            return rds
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", side_effect=_boto):
            resp = mod.handler(_event(), FakeContext())

        assert resp["statusCode"] == 200
        sns_mock.publish.assert_called_once()

    def test_lane_not_occupied_returns_409(self, mod):
        rds = make_member_rds({
            "FROM lanes WHERE id": {"records": _AVAILABLE_LANE},
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(_event(), FakeContext())

        assert resp["statusCode"] == 409

    def test_lane_not_found_returns_404(self, mod):
        rds = make_member_rds({
            "FROM lanes WHERE id": {"records": []},
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(_event(), FakeContext())

        assert resp["statusCode"] == 404

    def test_level_3_returns_403(self, mod):
        low = {"member_id": FAKE_MEMBER_ID, "sub": FAKE_SUB, "training_level": 3}
        with patch.object(mod, "authenticate_member", return_value=low):
            resp = mod.handler(_event(), FakeContext())

        assert resp["statusCode"] == 403

    def test_auth_failure_returns_403(self, mod):
        with patch.object(mod, "authenticate_member", side_effect=PermissionError("denied")):
            resp = mod.handler(_event(), FakeContext())

        assert resp["statusCode"] == 403

    def test_sns_failure_does_not_fail_request(self, mod):
        """SNS publish failure must be swallowed — 200 still returned."""
        rds = make_member_rds({
            "FROM lanes WHERE id": {"records": _OCCUPIED_LANE},
            "SET status = 'Available'": {"numberOfRecordsUpdated": 1},
            "Range-Checkout": {"numberOfRecordsUpdated": 1},
            "UPDATE wait_list": {"records": [[{"stringValue": "wl-id-1"}]]},
            "JOIN wait_list wl": {"records": [[{"stringValue": "+15555550100"}]]},
        })
        sns_mock = MagicMock()
        sns_mock.publish.side_effect = Exception("SNS unavailable")
        def _boto(svc, **kw):
            if svc == "sns":
                return sns_mock
            return rds
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", side_effect=_boto):
            resp = mod.handler(_event(), FakeContext())

        assert resp["statusCode"] == 200
