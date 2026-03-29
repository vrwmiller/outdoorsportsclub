"""Tests for functions/members/me-update/handler.py

PATCH /v1/members/me — partial update of authenticated member's profile fields.
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
    load_member_handler,
)
from tests.helpers import make_member_rds

_MOD_NAME = "member_me_update_handler"
_MEMBER = {"member_id": FAKE_MEMBER_ID, "sub": FAKE_SUB, "training_level": 3}


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def mod():
    m = load_member_handler("me-update")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", _MOD_NAME):
            del sys.modules[key]


def _patch_row(
    home_phone=None,
    mobile_phone="+15551234567",
    first_name="Alice",
    last_name="Smith",
    date_of_birth="1990-01-01",
    street_address="123 Main St",
    city="Springfield",
    state="IL",
    zip_="62701",
    notification_email=None,
    notify_email=True,
    notify_sms=False,
    notify_push=False,
) -> list:
    """Build a 13-column RETURNING row for UPDATE members."""
    def _s(v):
        return {"stringValue": v} if v is not None else {"isNull": True}

    return [
        _s(home_phone),
        _s(mobile_phone),
        _s(first_name),
        _s(last_name),
        _s(date_of_birth),
        _s(street_address),
        _s(city),
        _s(state),
        _s(zip_),
        _s(notification_email),
        {"booleanValue": notify_email},
        {"booleanValue": notify_sms},
        {"booleanValue": notify_push},
    ]


def _rds(row=None) -> MagicMock:
    """Return an rds mock that responds to UPDATE members with a 13-col row."""
    return make_member_rds({"UPDATE members": {"records": [row or _patch_row()]}})


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestPatchHappyPath:
    def test_update_mobile_phone_returns_200(self, mod):
        rds = _rds(_patch_row(mobile_phone="+15559876543"))
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event(body={"mobile_phone": "+15559876543"}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["mobile_phone"] == "+15559876543"

    def test_response_contains_all_13_fields(self, mod):
        rds = _rds()
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event(body={"mobile_phone": "+15551234567"}, method="PATCH"),
                FakeContext(),
            )

        body = json.loads(resp["body"])
        expected_keys = {
            "home_phone", "mobile_phone", "first_name", "last_name",
            "date_of_birth", "street_address", "city", "state", "zip",
            "notification_email", "notify_email", "notify_sms", "notify_push",
        }
        assert expected_keys == set(body.keys())

    def test_update_all_text_fields(self, mod):
        row = _patch_row(
            home_phone="+15550001111",
            mobile_phone="+15550002222",
            first_name="Bob",
            last_name="Jones",
            date_of_birth="1985-06-15",
            street_address="456 Oak Ave",
            city="Portland",
            state="OR",
            zip_="97201",
            notification_email="bob@example.com",
        )
        rds = _rds(row)
        payload = {
            "home_phone": "+15550001111",
            "mobile_phone": "+15550002222",
            "first_name": "Bob",
            "last_name": "Jones",
            "date_of_birth": "1985-06-15",
            "street_address": "456 Oak Ave",
            "city": "Portland",
            "state": "OR",
            "zip": "97201",
            "notification_email": "bob@example.com",
        }
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event(body=payload, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["first_name"] == "Bob"
        assert body["state"] == "OR"
        assert body["notification_email"] == "bob@example.com"

    def test_update_bool_fields(self, mod):
        row = _patch_row(notify_email=False, notify_sms=True, notify_push=True)
        rds = _rds(row)
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event(
                    body={"notify_email": False, "notify_sms": True, "notify_push": True},
                    method="PATCH",
                ),
                FakeContext(),
            )

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["notify_email"] is False
        assert body["notify_sms"] is True
        assert body["notify_push"] is True

    def test_null_value_clears_text_field(self, mod):
        row = _patch_row(home_phone=None)
        rds = _rds(row)
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event(body={"home_phone": None}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["home_phone"] is None

    def test_null_clears_non_phone_text_field(self, mod):
        """Null-clearing works for text fields beyond just phone numbers."""
        row = _patch_row(date_of_birth=None)
        rds = _rds(row)
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event(body={"date_of_birth": None}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["date_of_birth"] is None

    def test_state_normalised_to_uppercase(self, mod):
        row = _patch_row(state="CA")
        rds = _rds(row)
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event(body={"state": "ca"}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["state"] == "CA"

    def test_cors_headers_present(self, mod):
        rds = _rds()
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event(body={"mobile_phone": "+15551234567"}, method="PATCH"),
                FakeContext(),
            )

        assert "Access-Control-Allow-Origin" in resp["headers"]

    def test_commit_called_on_success(self, mod):
        rds = _rds()
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            mod.handler(
                member_jwt_event(body={"mobile_phone": "+15551234567"}, method="PATCH"),
                FakeContext(),
            )

        rds.commit_transaction.assert_called_once()


# ---------------------------------------------------------------------------
# Validation errors → 400
# ---------------------------------------------------------------------------

class TestPatchValidation:
    def test_invalid_mobile_phone_format(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_MEMBER):
            resp = mod.handler(
                member_jwt_event(body={"mobile_phone": "5551234567"}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_invalid_home_phone_format(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_MEMBER):
            resp = mod.handler(
                member_jwt_event(body={"home_phone": "+0123456789"}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_state_too_long(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_MEMBER):
            resp = mod.handler(
                member_jwt_event(body={"state": "CAL"}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_state_contains_digits(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_MEMBER):
            resp = mod.handler(
                member_jwt_event(body={"state": "1A"}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_blank_zip_rejected(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_MEMBER):
            resp = mod.handler(
                member_jwt_event(body={"zip": "   "}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_empty_string_zip_rejected(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_MEMBER):
            resp = mod.handler(
                member_jwt_event(body={"zip": ""}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_invalid_date_of_birth_format(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_MEMBER):
            resp = mod.handler(
                member_jwt_event(body={"date_of_birth": "01/01/1990"}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_impossible_calendar_date_rejected(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_MEMBER):
            resp = mod.handler(
                member_jwt_event(body={"date_of_birth": "2023-02-30"}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_invalid_notification_email(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_MEMBER):
            resp = mod.handler(
                member_jwt_event(body={"notification_email": "not-an-email"}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_bool_field_as_string_rejected(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_MEMBER):
            resp = mod.handler(
                member_jwt_event(body={"notify_email": "true"}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_bool_field_as_null_rejected(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_MEMBER):
            resp = mod.handler(
                member_jwt_event(body={"notify_sms": None}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_bool_field_as_integer_rejected(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_MEMBER):
            resp = mod.handler(
                member_jwt_event(body={"notify_push": 1}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_empty_body_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_MEMBER):
            resp = mod.handler(
                member_jwt_event(body={}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_no_body_returns_400(self, mod):
        with patch.object(mod, "authenticate_member", return_value=_MEMBER):
            resp = mod.handler(
                member_jwt_event(method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 400


# ---------------------------------------------------------------------------
# Protected fields are silently ignored
# ---------------------------------------------------------------------------

class TestPatchProtectedFields:
    def test_protected_fields_alone_return_400(self, mod):
        """Sending only non-updatable fields should be treated as no valid fields → 400."""
        with patch.object(mod, "authenticate_member", return_value=_MEMBER):
            resp = mod.handler(
                member_jwt_event(
                    body={"member_num": "HACK", "email": "evil@example.com", "training_level": 99},
                    method="PATCH",
                ),
                FakeContext(),
            )

        assert resp["statusCode"] == 400

    def test_protected_fields_alongside_valid_field_accepted(self, mod):
        """Protected extras are ignored; the valid field is applied → 200."""
        rds = _rds(_patch_row(mobile_phone="+15551234567"))
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event(
                    body={
                        "member_num": "HACK",
                        "training_level": 99,
                        "mobile_phone": "+15551234567",
                    },
                    method="PATCH",
                ),
                FakeContext(),
            )

        assert resp["statusCode"] == 200


# ---------------------------------------------------------------------------
# Auth failures → 403
# ---------------------------------------------------------------------------

class TestPatchAuth:
    def test_auth_failure_returns_403(self, mod):
        with patch.object(mod, "authenticate_member", side_effect=PermissionError("denied")):
            resp = mod.handler(
                member_jwt_event(body={"mobile_phone": "+15551234567"}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 403

    def test_403_response_has_cors_headers(self, mod):
        with patch.object(mod, "authenticate_member", side_effect=PermissionError("denied")):
            resp = mod.handler(
                member_jwt_event(body={"mobile_phone": "+15551234567"}, method="PATCH"),
                FakeContext(),
            )

        assert "Access-Control-Allow-Origin" in resp["headers"]


# ---------------------------------------------------------------------------
# DB / runtime errors → 500
# ---------------------------------------------------------------------------

class TestPatchDBError:
    def _failing_rds(self) -> MagicMock:
        rds = MagicMock()
        rds.begin_transaction.return_value = {"transactionId": "tx-1"}
        rds.execute_statement.side_effect = RuntimeError("DB connection lost")
        rds.rollback_transaction.return_value = {}
        return rds

    def test_db_error_returns_500(self, mod):
        rds = self._failing_rds()
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event(body={"mobile_phone": "+15551234567"}, method="PATCH"),
                FakeContext(),
            )

        assert resp["statusCode"] == 500

    def test_db_error_triggers_rollback(self, mod):
        rds = self._failing_rds()
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            mod.handler(
                member_jwt_event(body={"mobile_phone": "+15551234567"}, method="PATCH"),
                FakeContext(),
            )

        rds.rollback_transaction.assert_called_once()

    def test_db_error_has_cors_headers(self, mod):
        rds = self._failing_rds()
        with patch.object(mod, "authenticate_member", return_value=_MEMBER), \
             patch("boto3.client", return_value=rds):
            resp = mod.handler(
                member_jwt_event(body={"mobile_phone": "+15551234567"}, method="PATCH"),
                FakeContext(),
            )

        assert "Access-Control-Allow-Origin" in resp["headers"]
