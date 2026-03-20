"""POST /v1/kiosk/consumable-purchase

Records one or more line items to consumable_purchases.
For NFC/Card: verifies the Stripe Terminal PaymentIntent succeeded before inserting.
For Cash: inserts immediately on RSO confirmation.
member_id is optional (omit for anonymous guest purchases).

Expected request body:
    {
        "item_name": "<str>",
        "quantity": <int>,
        "unit_price": <float>,
        "payment_method": "Cash" | "NFC" | "Card",
        "stripe_payment_intent_id": "<str>",  # required for NFC/Card
        "member_num": "<str>"                 # optional — omit for guest
    }
"""
import json
import logging
import os
import time
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
        item_name: str | None = body.get("item_name")
        quantity = body.get("quantity")
        unit_price = body.get("unit_price")
        payment_method: str | None = body.get("payment_method")

        if not all([item_name, quantity is not None, unit_price is not None, payment_method]):
            raise ValueError("Required fields: item_name, quantity, unit_price, payment_method")
        if payment_method not in _VALID_PAYMENT_METHODS:
            raise ValueError(f"payment_method must be one of: {', '.join(_VALID_PAYMENT_METHODS)}")
        if not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("quantity must be a positive integer")
        if not isinstance(unit_price, (int, float)) or unit_price < 0:
            raise ValueError("unit_price must be a non-negative number")

        # Compute total server-side — never trust client-supplied total
        total: float = round(quantity * unit_price, 2)

        stripe_intent_id = body.get("stripe_payment_intent_id")
        if payment_method in ("NFC", "Card") and not stripe_intent_id:
            raise ValueError("stripe_payment_intent_id is required for NFC and Card payments")

        rds = boto3.client("rds-data")

        # Verify Stripe payment before opening the write transaction
        if payment_method in ("NFC", "Card"):
            if not _STRIPE_SECRET_ARN:
                raise ValueError("Stripe is not configured for this environment")
            sm = boto3.client("secretsmanager")
            stripe_secret = sm.get_secret_value(SecretId=_STRIPE_SECRET_ARN)["SecretString"]
            import stripe as _stripe
            _stripe.api_key = stripe_secret
            intent = _stripe.PaymentIntent.retrieve(stripe_intent_id)
            expected_amount = int(round(total * 100))
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
                    "(id, member_id, device_id, item_name, quantity, unit_price, total, "
                    "stripe_payment_intent_id, payment_method, timestamp) "
                    "VALUES (gen_random_uuid(), :member_id, :device_id, :item_name, "
                    ":quantity, :unit_price, :total, :stripe_intent, :payment_method, now())"
                ),
                parameters=[
                    {"name": "member_id", "value": (
                        {"stringValue": member_id} if member_id else {"isNull": True}
                    )},
                    {"name": "device_id", "value": {"stringValue": device_id}},
                    {"name": "item_name", "value": {"stringValue": item_name}},
                    {"name": "quantity", "value": {"longValue": quantity}},
                    {"name": "unit_price", "value": {"doubleValue": unit_price}},
                    {"name": "total", "value": {"doubleValue": total}},
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
