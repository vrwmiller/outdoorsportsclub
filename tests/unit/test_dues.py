"""Tests for functions/kiosk/dues/handler.py

POST /v1/kiosk/dues — annual dues payment via Cash (200) or NFC/Card (202).
"""
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import FakeContext, device_event, load_kiosk_handler, FAKE_STRIPE_KEY
from tests.helpers import make_rds


ANNUAL_DUES_CENTS = 5000


@pytest.fixture()
def mod():
    m = load_kiosk_handler("dues")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", "kiosk_dues_handler"):
            del sys.modules[key]


def _rds_cash():
    return make_rds({
        "set_config": {"records": []},
        "FROM members WHERE member_num": {"records": [[{"stringValue": "member-id-1"}]]},
        "FROM club_settings": {"records": [[{"longValue": ANNUAL_DUES_CENTS}]]},
        "UPDATE members SET dues_paid_until": {"numberOfRecordsUpdated": 1},
        "INSERT INTO activity_logs": {"numberOfRecordsUpdated": 1},
    })


def _rds_nfc():
    # NFC path reads member + club_settings then commits; same SQL as cash up to that point
    return _rds_cash()


def _sm_mock():
    sm = MagicMock()
    sm.get_secret_value.return_value = {"SecretString": FAKE_STRIPE_KEY}
    return sm


def _client_factory_nfc(rds_mock, sm_mock):
    def _factory(svc, **_):
        if svc == "secretsmanager":
            return sm_mock
        return rds_mock
    return _factory


class TestDues:
    def test_happy_path_cash(self, mod):
        rds = _rds_cash()
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(
                device_event({"member_num": "M001", "payment_method": "Cash"}),
                FakeContext(),
            )
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert "dues_paid_until" in body

    def test_happy_path_nfc(self, mod):
        rds = _rds_nfc()
        sm = _sm_mock()
        mock_intent = {"id": "pi_test_nfc"}
        with patch("boto3.client", side_effect=_client_factory_nfc(rds, sm)):
            with patch("stripe.PaymentIntent.create", return_value=mock_intent):
                resp = mod.handler(
                    device_event({"member_num": "M001", "payment_method": "NFC"}),
                    FakeContext(),
                )
        assert resp["statusCode"] == 202
        body = json.loads(resp["body"])
        assert body["payment_intent_id"] == "pi_test_nfc"

    def test_happy_path_card(self, mod):
        rds = _rds_nfc()
        sm = _sm_mock()
        mock_intent = {"id": "pi_test_card"}
        with patch("boto3.client", side_effect=_client_factory_nfc(rds, sm)):
            with patch("stripe.PaymentIntent.create", return_value=mock_intent):
                resp = mod.handler(
                    device_event({"member_num": "M001", "payment_method": "Card"}),
                    FakeContext(),
                )
        assert resp["statusCode"] == 202

    def test_missing_device_token_returns_403(self, mod):
        event = {
            "httpMethod": "POST",
            "headers": {},
            "body": json.dumps({"member_num": "M001", "payment_method": "Cash"}),
            "pathParameters": {},
        }
        rds = MagicMock()
        rds.execute_statement.return_value = {"records": []}
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(event, FakeContext())
        assert resp["statusCode"] == 403

    def test_missing_member_num_returns_400(self, mod):
        rds = make_rds({})  # auto-injects device auth
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(device_event({"payment_method": "Cash"}), FakeContext())
        assert resp["statusCode"] == 400

    def test_non_string_member_num_returns_400(self, mod):
        rds = make_rds({})  # ValueError raised before any DB query
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(device_event({"member_num": 12345, "payment_method": "Cash"}), FakeContext())
        assert resp["statusCode"] == 400

    def test_overlong_member_num_returns_400(self, mod):
        rds = make_rds({})  # ValueError raised before any DB query
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(device_event({"member_num": "A" * 65, "payment_method": "Cash"}), FakeContext())
        assert resp["statusCode"] == 400

    def test_invalid_payment_method_returns_400(self, mod):
        rds = make_rds({})  # auto-injects device auth
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(
                device_event({"member_num": "M001", "payment_method": "Bitcoin"}),
                FakeContext(),
            )
        assert resp["statusCode"] == 400

    def test_unknown_member_returns_404(self, mod):
        rds = make_rds({
            "set_config": {"records": []},
            "FROM members WHERE member_num": {"records": []},
        })
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(
                device_event({"member_num": "UNKNOWN", "payment_method": "Cash"}),
                FakeContext(),
            )
        assert resp["statusCode"] == 404

    def test_aws_failure_returns_500(self, mod):
        rds = MagicMock()
        rds.execute_statement.side_effect = Exception("DB offline")
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(
                device_event({"member_num": "M001", "payment_method": "Cash"}),
                FakeContext(),
            )
        assert resp["statusCode"] == 500

    def test_cors_headers_present(self, mod):
        rds = MagicMock()
        rds.execute_statement.return_value = {"records": []}
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(
                device_event({"member_num": "M001", "payment_method": "Cash"}),
                FakeContext(),
            )
        assert "Access-Control-Allow-Origin" in resp["headers"]
