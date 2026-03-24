"""Tests for functions/kiosk/consumable-purchase/handler.py

POST /v1/kiosk/consumable-purchase — records a consumable purchase (Cash or Stripe Terminal).
"""
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import FakeContext, device_event, load_kiosk_handler, FAKE_STRIPE_KEY
from tests.helpers import make_rds

FAKE_ITEM_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
UNIT_PRICE_CENTS = 250  # $2.50


@pytest.fixture()
def mod():
    m = load_kiosk_handler("consumable-purchase")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", "kiosk_consumable-purchase_handler"):
            del sys.modules[key]


def _rds_happy(*, with_member: bool = False):
    responses = {
        "FROM consumable_items WHERE id": {"records": [
            [{"stringValue": "Range Targets"}, {"longValue": UNIT_PRICE_CENTS}]
        ]},
        "set_config": {"records": []},
        "INSERT INTO consumable_purchases": {"numberOfRecordsUpdated": 1},
    }
    if with_member:
        responses["FROM members WHERE member_num"] = {"records": [[{"stringValue": "member-id-1"}]]}
    return make_rds(responses)


def _sm_mock():
    sm = MagicMock()
    sm.get_secret_value.return_value = {"SecretString": FAKE_STRIPE_KEY}
    return sm


def _client_factory(rds_mock, sm_mock=None):
    def _factory(svc, **_):
        if svc == "secretsmanager" and sm_mock is not None:
            return sm_mock
        return rds_mock
    return _factory


class TestConsumablePurchase:
    def test_happy_path_cash_anonymous(self, mod):
        rds = _rds_happy()
        with patch("boto3.client", side_effect=_client_factory(rds)):
            resp = mod.handler(
                device_event({"item_id": FAKE_ITEM_ID, "quantity": 1, "payment_method": "Cash"}),
                FakeContext(),
            )
        assert resp["statusCode"] == 200

    def test_happy_path_cash_with_member(self, mod):
        rds = _rds_happy(with_member=True)
        with patch("boto3.client", side_effect=_client_factory(rds)):
            resp = mod.handler(
                device_event({
                    "item_id": FAKE_ITEM_ID,
                    "quantity": 2,
                    "payment_method": "Cash",
                    "member_num": "M001",
                }),
                FakeContext(),
            )
        assert resp["statusCode"] == 200

    def test_happy_path_nfc_verified(self, mod):
        rds = _rds_happy()
        sm = _sm_mock()
        mock_intent = {"status": "succeeded", "amount": UNIT_PRICE_CENTS * 1}
        with patch("boto3.client", side_effect=_client_factory(rds, sm)):
            with patch("stripe.PaymentIntent.retrieve", return_value=mock_intent):
                resp = mod.handler(
                    device_event({
                        "item_id": FAKE_ITEM_ID,
                        "quantity": 1,
                        "payment_method": "NFC",
                        "stripe_payment_intent_id": "pi_test",
                    }),
                    FakeContext(),
                )
        assert resp["statusCode"] == 200

    def test_missing_device_token_returns_403(self, mod):
        event = {
            "httpMethod": "POST",
            "headers": {},
            "body": json.dumps({"item_id": FAKE_ITEM_ID, "quantity": 1, "payment_method": "Cash"}),
            "pathParameters": {},
        }
        rds = MagicMock()
        rds.execute_statement.return_value = {"records": []}
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(event, FakeContext())
        assert resp["statusCode"] == 403

    def test_missing_item_id_returns_400(self, mod):
        rds = make_rds({})  # auto-injects device auth; other queries unused
        with patch("boto3.client", side_effect=_client_factory(rds)):
            resp = mod.handler(
                device_event({"quantity": 1, "payment_method": "Cash"}),
                FakeContext(),
            )
        assert resp["statusCode"] == 400

    def test_invalid_item_id_uuid_returns_400(self, mod):
        rds = make_rds({})  # ValueError raised before any RDS query
        with patch("boto3.client", side_effect=_client_factory(rds)):
            resp = mod.handler(
                device_event({"item_id": "not-a-uuid", "quantity": 1, "payment_method": "Cash"}),
                FakeContext(),
            )
        assert resp["statusCode"] == 400

    def test_nfc_missing_stripe_intent_returns_400(self, mod):
        rds = make_rds({})  # ValueError raised before Stripe call
        with patch("boto3.client", side_effect=_client_factory(rds)):
            resp = mod.handler(
                device_event({"item_id": FAKE_ITEM_ID, "quantity": 1, "payment_method": "NFC"}),
                FakeContext(),
            )
        assert resp["statusCode"] == 400

    def test_inactive_item_returns_400(self, mod):
        # consumable_items lookup returns no rows (item not found / inactive)
        rds = make_rds({
            "FROM consumable_items WHERE id": {"records": []},
        })
        with patch("boto3.client", side_effect=_client_factory(rds)):
            resp = mod.handler(
                device_event({"item_id": FAKE_ITEM_ID, "quantity": 1, "payment_method": "Cash"}),
                FakeContext(),
            )
        assert resp["statusCode"] == 400

    def test_unconfirmed_stripe_intent_returns_402(self, mod):
        rds = _rds_happy()
        sm = _sm_mock()
        bad_intent = {"status": "requires_capture", "amount": UNIT_PRICE_CENTS}
        with patch("boto3.client", side_effect=_client_factory(rds, sm)):
            with patch("stripe.PaymentIntent.retrieve", return_value=bad_intent):
                resp = mod.handler(
                    device_event({
                        "item_id": FAKE_ITEM_ID,
                        "quantity": 1,
                        "payment_method": "Card",
                        "stripe_payment_intent_id": "pi_bad",
                    }),
                    FakeContext(),
                )
        assert resp["statusCode"] == 402

    def test_aws_failure_returns_500(self, mod):
        rds = MagicMock()
        rds.execute_statement.side_effect = Exception("DB offline")
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(
                device_event({"item_id": FAKE_ITEM_ID, "quantity": 1, "payment_method": "Cash"}),
                FakeContext(),
            )
        assert resp["statusCode"] == 500

    def test_cors_headers_present(self, mod):
        rds = MagicMock()
        rds.execute_statement.return_value = {"records": []}
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(
                device_event({"item_id": FAKE_ITEM_ID, "quantity": 1, "payment_method": "Cash"}),
                FakeContext(),
            )
        assert "Access-Control-Allow-Origin" in resp["headers"]

    def test_duplicate_stripe_intent_returns_409(self, mod):
        dup_msg = (
            "duplicate key value violates unique constraint "
            '"idx_consumable_purchases_stripe_payment_intent_id"'
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
            if "FROM consumable_items WHERE id" in sql:
                return {
                    "records": [[{"stringValue": "Range Targets"}, {"longValue": UNIT_PRICE_CENTS}]]
                }
            if "set_config" in sql:
                return {"records": []}
            if "INSERT INTO consumable_purchases" in sql:
                raise Exception(dup_msg)
            return {"records": []}

        rds.execute_statement.side_effect = _side_effect
        rds.begin_transaction.return_value = {"transactionId": "tx-1"}
        rds.rollback_transaction.return_value = {}

        sm = _sm_mock()
        good_intent = {"status": "succeeded", "amount": UNIT_PRICE_CENTS}

        with patch("boto3.client", side_effect=_client_factory(rds, sm)), \
                patch("stripe.PaymentIntent.retrieve", return_value=good_intent):
            resp = mod.handler(
                device_event({
                    "item_id": FAKE_ITEM_ID,
                    "quantity": 1,
                    "payment_method": "Card",
                    "stripe_payment_intent_id": "pi_dup",
                }),
                FakeContext(),
            )

        assert resp["statusCode"] == 409
        assert json.loads(resp["body"]) == {"error": "Payment intent already processed"}
