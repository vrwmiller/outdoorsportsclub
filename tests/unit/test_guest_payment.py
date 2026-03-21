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
FAKE_LANE_ID = "lane-id-1"
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
            "metadata": {},
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

