"""POST /v1/kiosk/consumable-purchase

Records one or more line items to consumable_purchases.
For NFC/Card: verifies the Stripe Terminal PaymentIntent succeeded before inserting.
For Cash: inserts immediately on RSO confirmation.
member_id is optional (omit for anonymous guest purchases).

Expected request body:
    {
        "item_id": "<uuid>",                  # must exist in consumable_items with is_active = true
        "quantity": <int>,
        "payment_method": "Cash" | "NFC" | "Card",
        "stripe_payment_intent_id": "<str>",  # required for NFC/Card
        "member_num": "<str>"                 # optional — omit for guest
    }
"""
import json
import logging
import os
import time
import uuid
from decimal import Decimal
from typing import Any

import boto3

from _auth import (
    DB_CLUSTER_ARN,
    DB_SECRET_ARN,
    DB_NAME,
    CORS_HEADERS,
    authenticate_device,
    error_response,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_STRIPE_SECRET_ARN: str = os.environ.get("STRIPE_SECRET_ARN", "")
_VALID_PAYMENT_METHODS = {"Cash", "NFC", "Card"}


def handler(event: dict, context: Any) -> dict:
    start = time.monotonic()
    member_id: str | None = None
    stripe_intent_id: str | None = None
    error_name: str | None = None

    try:
        device = authenticate_device(event)
        device_id: str = device["id"]

        body = json.loads(event.get("body") or "{}")
        item_id: str | None = body.get("item_id")
        quantity = body.get("quantity")
        payment_method: str | None = body.get("payment_method")

        if not all([item_id, quantity is not None, payment_method]):
            raise ValueError("Required fields: item_id, quantity, payment_method")
        if payment_method not in _VALID_PAYMENT_METHODS:
            raise ValueError(f"payment_method must be one of: {', '.join(_VALID_PAYMENT_METHODS)}")
        if not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("quantity must be a positive integer")
        try:
            uuid.UUID(item_id)
        except (ValueError, AttributeError):
            raise ValueError("item_id must be a valid UUID")

        stripe_intent_id = body.get("stripe_payment_intent_id")
        if payment_method in ("NFC", "Card") and not stripe_intent_id:
            raise ValueError("stripe_payment_intent_id is required for NFC and Card payments")

        rds = boto3.client("rds-data")

        # Look up item from catalog — price is always server-side, never from the request
        item_result = rds.execute_statement(
            resourceArn=DB_CLUSTER_ARN,
            secretArn=DB_SECRET_ARN,
            database=DB_NAME,
            sql="SELECT name, unit_price_cents FROM consumable_items WHERE id = :item_id AND is_active = TRUE",
            parameters=[{"name": "item_id", "value": {"stringValue": item_id}}],
        )
        if not item_result["records"]:
            raise ValueError("Unknown or inactive item")
        item_name: str = item_result["records"][0][0]["stringValue"]
        unit_price_cents: int = item_result["records"][0][1]["longValue"]

        # Use Decimal for exact monetary arithmetic — avoids float rounding drift
        unit_price: Decimal = Decimal(unit_price_cents) / Decimal(100)
        total: Decimal = unit_price * quantity

        # Verify Stripe payment before opening the write transaction
        if payment_method in ("NFC", "Card"):
            if not _STRIPE_SECRET_ARN:
                raise ValueError("Stripe is not configured for this environment")
            sm = boto3.client("secretsmanager")
            stripe_secret = sm.get_secret_value(SecretId=_STRIPE_SECRET_ARN)["SecretString"]
            import stripe as _stripe
            _stripe.api_key = stripe_secret
            intent = _stripe.PaymentIntent.retrieve(stripe_intent_id)
            expected_amount = unit_price_cents * quantity
            if intent["status"] != "succeeded" or intent["amount"] != expected_amount:
                duration_ms = int((time.monotonic() - start) * 1000)
                logger.warning(json.dumps({
                    "request_id": context.aws_request_id,
                    "member_id": member_id,
                    "device_id": device_id,
                    "action": "consumable_purchase",
                    "stripe_payment_intent_id": stripe_intent_id,
                    "duration_ms": duration_ms,
                    "error": "payment_not_confirmed",
                }))
                return {
                    "statusCode": 402,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"error": "Payment not confirmed"}),
                }

        tx = rds.begin_transaction(
            resourceArn=DB_CLUSTER_ARN, secretArn=DB_SECRET_ARN, database=DB_NAME
        )
        try:
            # Set RLS session variable — kiosk acts with training_level 4 (admin).
            rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql="SELECT set_config('app.current_training_level', '4', true)",
            )

            # Resolve optional member
            member_num: str | None = body.get("member_num")
            if member_num:
                m_result = rds.execute_statement(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    database=DB_NAME,
                    transactionId=tx["transactionId"],
                    sql="SELECT id FROM members WHERE member_num = :member_num",
                    parameters=[
                        {"name": "member_num", "value": {"stringValue": member_num}}
                    ],
                )
                if not m_result["records"]:
                    raise ValueError("Unknown member badge")
                member_id = m_result["records"][0][0]["stringValue"]

            rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql=(
                    "INSERT INTO consumable_purchases "
                    "(id, member_id, device_id, item_id, item_name, quantity, unit_price, total, "
                    "stripe_payment_intent_id, payment_method, timestamp) "
                    "VALUES (gen_random_uuid(), :member_id, :device_id, :item_id, :item_name, "
                    ":quantity, :unit_price, :total, :stripe_intent, :payment_method, now())"
                ),
                parameters=[
                    {"name": "member_id", "value": (
                        {"stringValue": member_id} if member_id else {"isNull": True}
                    )},
                    {"name": "device_id", "value": {"stringValue": device_id}},
                    {"name": "item_id", "value": {"stringValue": item_id}},
                    {"name": "item_name", "value": {"stringValue": item_name}},
                    {"name": "quantity", "value": {"longValue": quantity}},
                    {"name": "unit_price", "value": {"stringValue": str(unit_price)}},
                    {"name": "total", "value": {"stringValue": str(total)}},
                    {"name": "stripe_intent", "value": (
                        {"stringValue": stripe_intent_id} if stripe_intent_id
                        else {"isNull": True}
                    )},
                    {"name": "payment_method", "value": {"stringValue": payment_method}},
                ],
            )

            rds.commit_transaction(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                transactionId=tx["transactionId"],
            )
        except Exception:
            rds.rollback_transaction(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                transactionId=tx["transactionId"],
            )
            raise

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": device_id,
            "action": "consumable_purchase",
            "stripe_payment_intent_id": stripe_intent_id,
            "duration_ms": duration_ms,
            "error": None,
        }))
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Purchase recorded"}),
        }

    except PermissionError as exc:
        error_name = type(exc).__name__
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": None,
            "action": "consumable_purchase",
            "stripe_payment_intent_id": stripe_intent_id,
            "duration_ms": duration_ms,
            "error": error_name,
        }))
        return error_response(403, str(exc))
    except ValueError as exc:
        error_name = type(exc).__name__
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": None,
            "action": "consumable_purchase",
            "stripe_payment_intent_id": stripe_intent_id,
            "duration_ms": duration_ms,
            "error": error_name,
        }))
        return error_response(400, str(exc))
    except Exception as exc:  # noqa: BLE001
        error_name = type(exc).__name__
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.exception(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": None,
            "action": "consumable_purchase",
            "stripe_payment_intent_id": stripe_intent_id,
            "duration_ms": duration_ms,
            "error": error_name,
        }))
        return error_response(500, "Internal server error")
