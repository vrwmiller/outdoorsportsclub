"""Tests for functions/kiosk/guest-payment/handler.py

POST /v1/kiosk/guest-payment — guest add-on: upsert guest, check waiver, enforce annual
limit (≤ 2), verify Stripe intent for NFC/Card, record visit.
"""
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import FakeContext, device_event, load_kiosk_handler, FAKE_STRIPE_KEY
from tests.helpers import make_rds

FAKE_MEMBER_ID = "member-id-1"
FAKE_GUEST_ID = "guest-id-1"
FAKE_LANE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
GUEST_FEE_CENTS = 1000
VALID_WAIVER_DATE = "2026-02-19T00:00:00+00:00"


def _base_body(**overrides):
    body = {
        "member_num": "M001",
        "lane_id": FAKE_LANE_ID,
        "first_name": "Jane",
        "last_name": "Doe",
        "phone": "+15555550100",
        "email": "jane@example.com",
        "payment_method": "Cash",
    }
    body.update(overrides)
    return body


@pytest.fixture()
def mod():
    m = load_kiosk_handler("guest-payment")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", "kiosk_guest-payment_handler"):
            del sys.modules[key]


def _rds_happy(*, visit_count: int = 0):
    """RDS mock for the full happy-path guest-payment flow."""
    return make_rds({
        "set_config": {"records": []},
        "FROM members WHERE member_num": {"records": [[{"stringValue": FAKE_MEMBER_ID}]]},
        "FROM lanes": {"records": [[{"stringValue": FAKE_LANE_ID}]]},
        "INSERT INTO guests": {"records": [
            [{"stringValue": FAKE_GUEST_ID}, {"stringValue": VALID_WAIVER_DATE}]
        ]},
        "FROM club_settings": {"records": [[{"longValue": GUEST_FEE_CENTS}]]},
        "SET TRANSACTION ISOLATION LEVEL": {"records": []},
        "COUNT(*) FROM guest_visits": {"records": [[{"longValue": visit_count}]]},
        "INSERT INTO guest_visits": {"numberOfRecordsUpdated": 1},
        "INSERT INTO activity_logs": {"numberOfRecordsUpdated": 1},
    })


def _sm_mock():
    sm = MagicMock()
    sm.get_secret_value.return_value = {"SecretString": FAKE_STRIPE_KEY}
    return sm


def _client_factory(rds_mock, sm_mock=None):
    def _factory(svc, **_):
        if svc == "secretsmanager" and sm_mock:
            return sm_mock
        return rds_mock
    return _factory


class TestGuestPayment:
    def test_happy_path_cash(self, mod):
        rds = _rds_happy()
        with patch("boto3.client", side_effect=_client_factory(rds)):
            resp = mod.handler(device_event(_base_body()), FakeContext())
        assert resp["statusCode"] == 200

    def test_happy_path_nfc_verified_intent(self, mod):
        rds = _rds_happy()
        sm = _sm_mock()
        mock_intent = {
            "status": "succeeded",
            "amount": GUEST_FEE_CENTS,
            "currency": "usd",
            "metadata": {"device_id": "device-id-1", "member_num": "M001"},
        }
        with patch("boto3.client", side_effect=_client_factory(rds, sm)):
            with patch("stripe.PaymentIntent.retrieve", return_value=mock_intent):
                resp = mod.handler(
                    device_event(_base_body(
                        payment_method="NFC",
                        stripe_payment_intent_id="pi_test",
                    )),
                    FakeContext(),
                )
        assert resp["statusCode"] == 200

    def test_missing_device_token_returns_403(self, mod):
        event = {
            "httpMethod": "POST",
            "headers": {},
            "body": json.dumps(_base_body()),
            "pathParameters": {},
        }
        rds = MagicMock()
        rds.execute_statement.return_value = {"records": []}
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(event, FakeContext())
        assert resp["statusCode"] == 403

    def test_missing_required_field_returns_400(self, mod):
        body = _base_body()
        del body["first_name"]
        rds = make_rds({})  # auto-injects device auth; ValueError raised before DB queries
        with patch("boto3.client", side_effect=_client_factory(rds)):
            resp = mod.handler(device_event(body), FakeContext())
        assert resp["statusCode"] == 400

    def test_non_string_member_num_returns_400(self, mod):
        body = _base_body(member_num=12345)
        rds = make_rds({})  # ValueError raised before any DB query
        with patch("boto3.client", side_effect=_client_factory(rds)):
            resp = mod.handler(device_event(body), FakeContext())
        assert resp["statusCode"] == 400

    def test_overlong_member_num_returns_400(self, mod):
        body = _base_body(member_num="A" * 65)
        rds = make_rds({})  # ValueError raised before any DB query
        with patch("boto3.client", side_effect=_client_factory(rds)):
            resp = mod.handler(device_event(body), FakeContext())
        assert resp["statusCode"] == 400

    def test_non_string_lane_id_returns_400(self, mod):
        body = _base_body(lane_id=12345)
        rds = make_rds({})
        with patch("boto3.client", side_effect=_client_factory(rds)):
            resp = mod.handler(device_event(body), FakeContext())
        assert resp["statusCode"] == 400

    def test_invalid_uuid_lane_id_returns_400(self, mod):
        body = _base_body(lane_id="not-a-uuid")
        rds = make_rds({})
        with patch("boto3.client", side_effect=_client_factory(rds)):
            resp = mod.handler(device_event(body), FakeContext())
        assert resp["statusCode"] == 400

    def test_non_string_first_name_returns_400(self, mod):
        body = _base_body(first_name=42)
        rds = make_rds({})
        with patch("boto3.client", side_effect=_client_factory(rds)):
            resp = mod.handler(device_event(body), FakeContext())
        assert resp["statusCode"] == 400

    def test_overlong_first_name_returns_400(self, mod):
        body = _base_body(first_name="A" * 101)
        rds = make_rds({})
        with patch("boto3.client", side_effect=_client_factory(rds)):
            resp = mod.handler(device_event(body), FakeContext())
        assert resp["statusCode"] == 400

    def test_overlong_phone_returns_400(self, mod):
        body = _base_body(phone="1" * 21)
        rds = make_rds({})
        with patch("boto3.client", side_effect=_client_factory(rds)):
            resp = mod.handler(device_event(body), FakeContext())
        assert resp["statusCode"] == 400

    def test_overlong_email_returns_400(self, mod):
        body = _base_body(email="a" * 321)
        rds = make_rds({})
        with patch("boto3.client", side_effect=_client_factory(rds)):
            resp = mod.handler(device_event(body), FakeContext())
        assert resp["statusCode"] == 400

    def test_nfc_missing_stripe_intent_returns_400(self, mod):
        rds = make_rds({})  # ValueError raised before DB queries
        with patch("boto3.client", side_effect=_client_factory(rds)):
            resp = mod.handler(
                device_event(_base_body(payment_method="NFC")),
                FakeContext(),
            )
        assert resp["statusCode"] == 400

    def test_unknown_member_returns_403(self, mod):
        rds = make_rds({
            "set_config": {"records": []},
            "FROM members WHERE member_num": {"records": []},
        })
        with patch("boto3.client", side_effect=_client_factory(rds)):
            resp = mod.handler(device_event(_base_body()), FakeContext())
        assert resp["statusCode"] == 403

    def test_annual_visit_limit_reached_returns_403(self, mod):
        rds = _rds_happy(visit_count=2)
        with patch("boto3.client", side_effect=_client_factory(rds)):
            resp = mod.handler(device_event(_base_body()), FakeContext())
        assert resp["statusCode"] == 403

    def test_unconfirmed_stripe_intent_returns_402(self, mod):
        rds = _rds_happy()
        sm = _sm_mock()
        bad_intent = {"status": "requires_payment_method", "amount": GUEST_FEE_CENTS, "currency": "usd", "metadata": {}}
        with patch("boto3.client", side_effect=_client_factory(rds, sm)):
            with patch("stripe.PaymentIntent.retrieve", return_value=bad_intent):
                resp = mod.handler(
                    device_event(_base_body(payment_method="NFC", stripe_payment_intent_id="pi_bad")),
                    FakeContext(),
                )
        assert resp["statusCode"] == 402

    def test_missing_metadata_returns_402(self, mod):
        # SEC-23: a succeeded intent with no metadata must be rejected — the guard
        # requires both device_id and member_num to be present and match.
        rds = _rds_happy()
        sm = _sm_mock()
        intent = {
            "status": "succeeded",
            "amount": GUEST_FEE_CENTS,
            "currency": "usd",
            "metadata": {},
        }
        with patch("boto3.client", side_effect=_client_factory(rds, sm)), patch(
            "stripe.PaymentIntent.retrieve", return_value=intent
        ):
            resp = mod.handler(
                device_event(_base_body(payment_method="NFC", stripe_payment_intent_id="pi_no_meta")),
                FakeContext(),
            )
        assert resp["statusCode"] == 402

    def test_mismatched_device_id_in_metadata_returns_402(self, mod):
        # SEC-23: metadata.device_id must match the request's device token.
        rds = _rds_happy()
        sm = _sm_mock()
        intent = {
            "status": "succeeded",
            "amount": GUEST_FEE_CENTS,
            "currency": "usd",
            "metadata": {"device_id": "wrong-device", "member_num": "M001"},
        }
        with patch("boto3.client", side_effect=_client_factory(rds, sm)), patch(
            "stripe.PaymentIntent.retrieve", return_value=intent
        ):
            resp = mod.handler(
                device_event(_base_body(payment_method="NFC", stripe_payment_intent_id="pi_wrong_device")),
                FakeContext(),
            )
        assert resp["statusCode"] == 402

    def test_mismatched_member_num_in_metadata_returns_402(self, mod):
        # SEC-23: metadata.member_num must match the member_num in the request body.
        rds = _rds_happy()
        sm = _sm_mock()
        intent = {
            "status": "succeeded",
            "amount": GUEST_FEE_CENTS,
            "currency": "usd",
            "metadata": {"device_id": "device-id-1", "member_num": "M999"},
        }
        with patch("boto3.client", side_effect=_client_factory(rds, sm)), patch(
            "stripe.PaymentIntent.retrieve", return_value=intent
        ):
            resp = mod.handler(
                device_event(_base_body(payment_method="NFC", stripe_payment_intent_id="pi_wrong_member")),
                FakeContext(),
            )
        assert resp["statusCode"] == 402

    def test_aws_failure_returns_500(self, mod):
        rds = MagicMock()
        rds.execute_statement.side_effect = Exception("DB offline")
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(device_event(_base_body()), FakeContext())
        assert resp["statusCode"] == 500

    def test_cors_headers_present(self, mod):
        rds = MagicMock()
        rds.execute_statement.return_value = {"records": []}
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(device_event(_base_body()), FakeContext())
        assert "Access-Control-Allow-Origin" in resp["headers"]

    def test_duplicate_stripe_intent_returns_409(self, mod):
        dup_msg = (
            "duplicate key value violates unique constraint "
            '"idx_guest_visits_stripe_payment_intent_id"'
        )
        rds = MagicMock()

        def _side_effect(**kwargs):
            sql = kwargs.get("sql", "")
            if "WHERE device_token" in sql:
                return {
                    "records": [
                        [
                            {"stringValue": "device-id-1"},
                            {"stringValue": "range-id-1"},
                            {"stringValue": "Active"},
                        ]
                    ]
                }
            if "SET TRANSACTION ISOLATION LEVEL" in sql:
                return {"records": []}
            if "set_config" in sql:
                return {"records": []}
            if "FROM members WHERE member_num" in sql:
                return {"records": [[{"stringValue": FAKE_MEMBER_ID}]]}
            if "FROM lanes" in sql:
                return {"records": [[{"stringValue": FAKE_LANE_ID}]]}
            if "INSERT INTO guests" in sql:
                return {
                    "records": [
                        [{"stringValue": FAKE_GUEST_ID}, {"stringValue": VALID_WAIVER_DATE}]
                    ]
                }
            if "FROM club_settings" in sql:
                return {"records": [[{"longValue": GUEST_FEE_CENTS}]]}
            if "COUNT(*) FROM guest_visits" in sql:
                return {"records": [[{"longValue": 0}]]}
            if "INSERT INTO guest_visits" in sql:
                raise Exception(dup_msg)
            return {"records": []}

        rds.execute_statement.side_effect = _side_effect
        rds.begin_transaction.return_value = {"transactionId": "tx-1"}
        rds.rollback_transaction.return_value = {}
        sm = _sm_mock()

        with patch("boto3.client", side_effect=_client_factory(rds, sm)), patch(
            "stripe.PaymentIntent.retrieve",
            return_value={
                "id": "pi_dup",
                "status": "succeeded",
                "amount": GUEST_FEE_CENTS,
                "currency": "usd",
                "metadata": {"device_id": "device-id-1", "member_num": "M001"},
            },
        ):
            resp = mod.handler(
                device_event(_base_body(payment_method="NFC", stripe_payment_intent_id="pi_dup")),
                FakeContext(),
            )

        assert resp["statusCode"] == 409
        assert json.loads(resp["body"]) == {"error": "Payment intent already processed"}

    def test_serialization_failure_retried_and_succeeds(self, mod):
        """First commit raises SQLSTATE 40001; second attempt succeeds — returns 200."""
        commit_calls = {"n": 0}

        def _commit(**kwargs):
            commit_calls["n"] += 1
            if commit_calls["n"] == 1:
                raise Exception("ERROR: could not serialize access due to concurrent update SQLSTATE 40001")
            return {}

        rds = _rds_happy()
        rds.commit_transaction.side_effect = _commit
        with patch("boto3.client", side_effect=_client_factory(rds)), patch("time.sleep") as mock_sleep:
            resp = mod.handler(device_event(_base_body()), FakeContext())
        assert resp["statusCode"] == 200
        # First attempt failed (40001) then retried — commit must have been called exactly twice.
        assert rds.commit_transaction.call_count == 2
        # Backoff sleep must have been called exactly once (between attempt 0 and attempt 1).
        assert mock_sleep.call_count == 1

    def test_serialization_failure_exhausted_returns_503(self, mod):
        """Three consecutive serialization failures return 503."""
        rds = _rds_happy()
        rds.commit_transaction.side_effect = Exception(
            "ERROR: could not serialize access SQLSTATE 40001"
        )
        with patch("boto3.client", side_effect=_client_factory(rds)), patch("time.sleep") as mock_sleep:
            resp = mod.handler(device_event(_base_body()), FakeContext())
        assert resp["statusCode"] == 503
        assert json.loads(resp["body"]) == {"error": "Service temporarily unavailable, please retry"}
        # All _MAX_TX_RETRIES attempts must have been made — no early bail-out.
        assert rds.commit_transaction.call_count == 3
        assert rds.begin_transaction.call_count == 3
        assert rds.rollback_transaction.call_count == 3
        # Backoff sleep fires between attempts 0→1 and 1→2 (not after the last failure).
        assert mock_sleep.call_count == 2

