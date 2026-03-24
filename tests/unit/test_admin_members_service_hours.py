"""Tests for functions/admin/members-service-hours/handler.py

PATCH /v1/admin/members/{member_id}/service-hours — Level 5+ sets service_hours.
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

_ADMIN = {"member_id": FAKE_MEMBER_ID, "sub": FAKE_SUB, "training_level": 5}

_MOD_NAME = "admin_members_service_hours_handler"

_TARGET_ID = "cccccccc-dddd-eeee-ffff-000000000002"


def _event(body, target_id=_TARGET_ID):
    return member_jwt_event(body, path_params={"member_id": target_id}, method="PATCH")


@pytest.fixture()
def mod():
    m = load_admin_handler("members-service-hours")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", _MOD_NAME):
            del sys.modules[key]


class TestAdminMembersServiceHours:
    def test_success_updates_hours(self, mod):
        rds = make_member_rds({
            "FROM members WHERE id = :tid": {"records": [[{"stringValue": _TARGET_ID}]]},
            "service_hours = :hours": {"records": [[{"stringValue": "4.50"}]]},
            "Service-Hours-Update": {"numberOfRecordsUpdated": 1},
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(_event({"service_hours": 4.5}), FakeContext())

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert "service_hours" in body

    def test_zero_hours_is_valid(self, mod):
        rds = make_member_rds({
            "FROM members WHERE id = :tid": {"records": [[{"stringValue": _TARGET_ID}]]},
            "service_hours = :hours": {"records": [[{"stringValue": "0.00"}]]},
            "Service-Hours-Update": {"numberOfRecordsUpdated": 1},
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(_event({"service_hours": 0}), FakeContext())

        assert resp["statusCode"] == 200

    def test_target_not_found_returns_404(self, mod):
        rds = make_member_rds({
            "FROM members WHERE id = :tid": {"records": []},
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(_event({"service_hours": 2}), FakeContext())

        assert resp["statusCode"] == 404

    def test_negative_hours_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(_event({"service_hours": -1}), FakeContext())

        assert resp["statusCode"] == 400

    def test_hours_above_limit_returns_400(self, mod):
        """service_hours above 999.99 (DECIMAL(5,2) max) must be rejected."""
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(_event({"service_hours": 1000}), FakeContext())

        assert resp["statusCode"] == 400

    def test_boolean_hours_returns_400(self, mod):
        """Boolean JSON values must be rejected (bool is subclass of int in Python)."""
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(_event({"service_hours": True}), FakeContext())

        assert resp["statusCode"] == 400

    def test_nan_hours_returns_400(self, mod):
        """NaN must be rejected — float('nan') comparisons are always False."""
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(_event({"service_hours": float("nan")}), FakeContext())

        assert resp["statusCode"] == 400

    def test_infinity_hours_returns_400(self, mod):
        """Infinity must be rejected."""
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(_event({"service_hours": float("inf")}), FakeContext())

        assert resp["statusCode"] == 400

    def test_missing_field_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(_event({}), FakeContext())

        assert resp["statusCode"] == 400

    def test_level_4_actor_returns_403(self, mod):
        low = {"member_id": FAKE_MEMBER_ID, "sub": FAKE_SUB, "training_level": 4}
        with patch.object(mod, "authenticate_member", return_value=low):
            resp = mod.handler(_event({"service_hours": 2}), FakeContext())

        assert resp["statusCode"] == 403

    def test_auth_failure_returns_403(self, mod):
        with patch.object(mod, "authenticate_member", side_effect=PermissionError("denied")):
            resp = mod.handler(_event({"service_hours": 2}), FakeContext())

        assert resp["statusCode"] == 403
