"""Tests for functions/admin/members-level/handler.py

PATCH /v1/admin/members/{member_id}/level — Level 5+ updates training_level.
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

_MOD_NAME = "admin_members_level_handler"

_TARGET_ID = "cccccccc-dddd-eeee-ffff-000000000001"


def _event(body, target_id=_TARGET_ID):
    return member_jwt_event(body, path_params={"member_id": target_id}, method="PATCH")


@pytest.fixture()
def mod():
    m = load_admin_handler("members-level")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", _MOD_NAME):
            del sys.modules[key]


class TestAdminMembersLevel:
    def test_success_updates_level(self, mod):
        rds = make_member_rds({
            # target is Level 3, actor is Level 5
            "FROM members WHERE id = :tid": {
                "records": [[{"stringValue": _TARGET_ID}, {"longValue": 3}]],
            },
            "training_level = :new_level": {"numberOfRecordsUpdated": 1},
            "Level-Change": {"numberOfRecordsUpdated": 1},
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(_event({"training_level": 4}), FakeContext())

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["member_id"] == _TARGET_ID
        assert body["training_level"] == 4

    def test_cannot_modify_higher_level_member_returns_403(self, mod):
        """Level 5 actor cannot modify a Level 5 or Level 6 member."""
        rds = make_member_rds({
            # target is Level 5, same as actor
            "FROM members WHERE id = :tid": {
                "records": [[{"stringValue": _TARGET_ID}, {"longValue": 5}]],
            },
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(_event({"training_level": 2}), FakeContext())

        assert resp["statusCode"] == 403

    def test_target_not_found_returns_404(self, mod):
        rds = make_member_rds({
            "FROM members WHERE id = :tid": {"records": []},
        })
        with patch.object(mod, "authenticate_member", return_value=_ADMIN), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(_event({"training_level": 2}), FakeContext())

        assert resp["statusCode"] == 404

    def test_level_out_of_range_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(_event({"training_level": 7}), FakeContext())

        assert resp["statusCode"] == 400

    def test_negative_level_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(_event({"training_level": -1}), FakeContext())

        assert resp["statusCode"] == 400

    def test_missing_level_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(_event({}), FakeContext())

        assert resp["statusCode"] == 400

    def test_level_4_actor_returns_403(self, mod):
        low = {"member_id": FAKE_MEMBER_ID, "sub": FAKE_SUB, "training_level": 4}
        with patch.object(mod, "authenticate_member", return_value=low):
            resp = mod.handler(_event({"training_level": 2}), FakeContext())

        assert resp["statusCode"] == 403

    def test_auth_failure_returns_403(self, mod):
        with patch.object(mod, "authenticate_member", side_effect=PermissionError("denied")):
            resp = mod.handler(_event({"training_level": 2}), FakeContext())

        assert resp["statusCode"] == 403

    def test_cannot_grant_own_level_returns_403(self, mod):
        """Level 5 actor cannot set any member to Level 5."""
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(_event({"training_level": 5}), FakeContext())

        assert resp["statusCode"] == 403

    def test_cannot_self_promote_to_level_6_returns_403(self, mod):
        """Level 5 actor cannot promote anyone (including self) to Level 6."""
        with patch.object(mod, "authenticate_member", return_value=_ADMIN):
            resp = mod.handler(_event({"training_level": 6}), FakeContext())

        assert resp["statusCode"] == 403
