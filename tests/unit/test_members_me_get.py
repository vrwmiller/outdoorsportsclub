"""Tests for the extended GET /v1/members/me response (migration 0025 fields).

These tests cover the 11 new profile columns added in migration 0025 and the
Cognito name claim fallback behaviour.  Core auth and DB-error-path tests are
covered in test_member_me.py and are not duplicated here.
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
    load_member_handler,
)
from tests.helpers import make_member_rds, full_member_profile_row

_MEMBER = {"member_id": FAKE_MEMBER_ID, "sub": FAKE_SUB, "training_level": 3}
_MEMBER_WITH_NAMES = {**_MEMBER, "given_name": "Alice", "family_name": "Smith"}

_MOD_NAME = "member_me_handler"


@pytest.fixture()
def mod():
    m = load_member_handler("me")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", _MOD_NAME):
            del sys.modules[key]


def _rds(row):
    return make_member_rds({
        "members WHERE id": {"records": [row]},
        "club_settings": {"records": [[{"longValue": 10000}]]},
    })


# ---------------------------------------------------------------------------
# New profile fields present in the response
# ---------------------------------------------------------------------------

class TestNewProfileFields:
    def test_all_profile_fields_returned(self, mod):
        row = full_member_profile_row(
            first_name="Bob",
            last_name="Jones",
            date_of_birth="1985-06-15",
            street_address="456 Oak Ave",
            city="Chicago",
            state="IL",
            zip="60601",
            notification_email="bob.work@example.com",
            notify_email=True,
            notify_sms=True,
            notify_push=False,
        )
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=_rds(row)):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["first_name"] == "Bob"
        assert body["last_name"] == "Jones"
        assert body["date_of_birth"] == "1985-06-15"
        assert body["street_address"] == "456 Oak Ave"
        assert body["city"] == "Chicago"
        assert body["state"] == "IL"
        assert body["zip"] == "60601"
        assert body["notification_email"] == "bob.work@example.com"
        assert body["notify_email"] is True
        assert body["notify_sms"] is True
        assert body["notify_push"] is False

    def test_nullable_profile_fields_return_none(self, mod):
        row = full_member_profile_row(
            date_of_birth=None,
            street_address=None,
            city=None,
            state=None,
            zip=None,
            notification_email=None,
        )
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=_rds(row)):
            resp = mod.handler(member_jwt_event(), FakeContext())

        body = json.loads(resp["body"])
        assert body["date_of_birth"] is None
        assert body["street_address"] is None
        assert body["city"] is None
        assert body["state"] is None
        assert body["zip"] is None
        assert body["notification_email"] is None

    def test_notify_defaults_are_correct_types(self, mod):
        # notify_email defaults to True; notify_sms and notify_push default to False.
        row = full_member_profile_row()
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=_rds(row)):
            resp = mod.handler(member_jwt_event(), FakeContext())

        body = json.loads(resp["body"])
        assert body["notify_email"] is True
        assert body["notify_sms"] is False
        assert body["notify_push"] is False

    def test_all_notify_flags_can_be_true(self, mod):
        row = full_member_profile_row(notify_email=True, notify_sms=True, notify_push=True)
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=_rds(row)):
            resp = mod.handler(member_jwt_event(), FakeContext())

        body = json.loads(resp["body"])
        assert body["notify_email"] is True
        assert body["notify_sms"] is True
        assert body["notify_push"] is True


# ---------------------------------------------------------------------------
# Cognito name claim fallback
# ---------------------------------------------------------------------------

class TestCognitoNameFallback:
    def test_first_name_falls_back_to_cognito_when_db_null(self, mod):
        row = full_member_profile_row(first_name=None, last_name="Jones")
        with patch.object(mod, "authenticate_member", return_value=_MEMBER_WITH_NAMES), \
             patch("boto3.client", return_value=_rds(row)):
            resp = mod.handler(member_jwt_event(), FakeContext())

        body = json.loads(resp["body"])
        assert body["first_name"] == "Alice"  # Cognito given_name
        assert body["last_name"] == "Jones"   # DB value

    def test_last_name_falls_back_to_cognito_when_db_null(self, mod):
        row = full_member_profile_row(first_name="Bob", last_name=None)
        with patch.object(mod, "authenticate_member", return_value=_MEMBER_WITH_NAMES), \
             patch("boto3.client", return_value=_rds(row)):
            resp = mod.handler(member_jwt_event(), FakeContext())

        body = json.loads(resp["body"])
        assert body["first_name"] == "Bob"    # DB value
        assert body["last_name"] == "Smith"   # Cognito family_name

    def test_both_names_fall_back_to_cognito_when_both_db_null(self, mod):
        row = full_member_profile_row(first_name=None, last_name=None)
        with patch.object(mod, "authenticate_member", return_value=_MEMBER_WITH_NAMES), \
             patch("boto3.client", return_value=_rds(row)):
            resp = mod.handler(member_jwt_event(), FakeContext())

        body = json.loads(resp["body"])
        assert body["first_name"] == "Alice"
        assert body["last_name"] == "Smith"

    def test_db_value_wins_over_cognito_claim(self, mod):
        # DB has names set — Cognito claims must not override them.
        row = full_member_profile_row(first_name="Robert", last_name="Brown")
        with patch.object(mod, "authenticate_member", return_value=_MEMBER_WITH_NAMES), \
             patch("boto3.client", return_value=_rds(row)):
            resp = mod.handler(member_jwt_event(), FakeContext())

        body = json.loads(resp["body"])
        assert body["first_name"] == "Robert"  # DB value, not "Alice"
        assert body["last_name"] == "Brown"    # DB value, not "Smith"

    def test_no_cognito_claims_and_db_null_returns_none(self, mod):
        # authenticate_member mock has no given_name/family_name (older shape).
        # Handler must handle missing keys gracefully and return None.
        row = full_member_profile_row(first_name=None, last_name=None)
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=_rds(row)):
            resp = mod.handler(member_jwt_event(), FakeContext())

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["first_name"] is None
        assert body["last_name"] is None
