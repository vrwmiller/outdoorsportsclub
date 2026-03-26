"""POST /v1/kiosk/dues

Kiosk path for annual dues payment via Stripe Terminal (NFC/Card) or Cash.

For Cash: writes dues_paid_until directly and returns 200.
For NFC/Card: creates a Stripe Terminal PaymentIntent and returns 202.
  The payment_intent.succeeded webhook confirms and sets dues_paid_until.

Expected request body:
    {
        "member_num": "<qr_badge_value>",
        "payment_method": "Cash" | "NFC" | "Card"
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
    MEMBER_NUM_MAX_LEN,
    authenticate_device,
    error_response,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_STRIPE_SECRET_ARN: str = os.environ.get("STRIPE_SECRET_ARN", "")
_stripe_key: str | None = None  # cached on first NFC/Card invocation per container
_VALID_PAYMENT_METHODS = {"Cash", "NFC", "Card"}


def handler(event: dict, context: Any) -> dict:
    start = time.monotonic()
    member_id: str | None = None
    device_id: str | None = None
    stripe_intent_id: str | None = None
    error_name: str | None = None

    try:
        device = authenticate_device(event)
        device_id = device["id"]

        body = json.loads(event.get("body") or "{}")
        member_num: str | None = body.get("member_num")
        if not member_num:
            raise ValueError("member_num is required")
        if not isinstance(member_num, str):
            raise ValueError("member_num must be a string")
        if len(member_num) > MEMBER_NUM_MAX_LEN:
            raise ValueError("member_num exceeds maximum length")
        payment_method: str | None = body.get("payment_method")
        if not payment_method:
            raise ValueError("payment_method is required")
        if payment_method not in _VALID_PAYMENT_METHODS:
            raise ValueError(f"payment_method must be one of: {', '.join(_VALID_PAYMENT_METHODS)}")

        import datetime

        rds = boto3.client("rds-data")

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

            # Resolve member
            m_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql="SELECT id FROM members WHERE member_num = :member_num",
                parameters=[{"name": "member_num", "value": {"stringValue": member_num}}],
            )
            if not m_result["records"]:
                rds.rollback_transaction(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    transactionId=tx["transactionId"],
                )
                duration_ms = int((time.monotonic() - start) * 1000)
                logger.warning(json.dumps({
                    "request_id": context.aws_request_id,
                    "member_id": None,
                    "device_id": device_id,
                    "action": "dues",
                    "stripe_payment_intent_id": None,
                    "duration_ms": duration_ms,
                    "error": "unknown_member",
                }))
                return {
                    "statusCode": 404,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"error": "Unknown member badge"}),
                }
            member_id = m_result["records"][0][0]["stringValue"]

            # Read annual dues amount from club_settings
            settings_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql="SELECT annual_dues_cents FROM club_settings WHERE singleton = TRUE",
            )
            if not settings_result["records"]:
                raise RuntimeError("club_settings row missing")
            annual_dues_cents: int = int(settings_result["records"][0][0]["longValue"])

            if payment_method == "Cash":
                rds.execute_statement(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    database=DB_NAME,
                    transactionId=tx["transactionId"],
                    sql=(
                        "UPDATE members "
                        "SET dues_paid_until = make_date(extract(year from (now() at time zone 'utc'))::int, 12, 31) "
                        "WHERE id = :member_id"
                    ),
                    parameters=[
                        {"name": "member_id", "value": {"stringValue": member_id}}
                    ],
                )
                rds.execute_statement(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    database=DB_NAME,
                    transactionId=tx["transactionId"],
                    sql=(
                        "INSERT INTO activity_logs "
                        "(member_id, device_id, activity_type, payment_method, timestamp) "
                        "VALUES (:member_id, :device_id, 'Dues-Payment', 'Cash', now())"
                    ),
                    parameters=[
                        {"name": "member_id", "value": {"stringValue": member_id}},
                        {"name": "device_id", "value": {"stringValue": device_id}},
                    ],
                )
                rds.commit_transaction(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    transactionId=tx["transactionId"],
                )
                # Compute the dues_paid_until value set by the SQL above (avoids a re-fetch).
                dues_paid_until = datetime.date(
                    datetime.datetime.now(tz=datetime.timezone.utc).year, 12, 31
                ).isoformat()
                duration_ms = int((time.monotonic() - start) * 1000)
                logger.info(json.dumps({
                    "request_id": context.aws_request_id,
                    "member_id": member_id,
                    "device_id": device_id,
                    "action": "dues",
                    "stripe_payment_intent_id": None,
                    "duration_ms": duration_ms,
                    "error": None,
                }))
                return {
                    "statusCode": 200,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"dues_paid_until": dues_paid_until}),
                }

            # NFC / Card: commit the read tx, then create a Stripe Terminal PaymentIntent.
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

        if not _STRIPE_SECRET_ARN:
            raise ValueError("Stripe is not configured for this environment")
        global _stripe_key
        if _stripe_key is None:
            sm = boto3.client("secretsmanager")
            _stripe_key = sm.get_secret_value(SecretId=_STRIPE_SECRET_ARN)["SecretString"]
        import stripe as _stripe
        _stripe.api_key = _stripe_key

        intent = _stripe.PaymentIntent.create(
            amount=annual_dues_cents,
            currency="usd",
            payment_method_types=["card_present"],
            capture_method="automatic",
            metadata={"member_id": member_id, "device_id": device_id, "type": "dues"},
        )
        stripe_intent_id = intent["id"]

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": device_id,
            "action": "dues",
            "stripe_payment_intent_id": stripe_intent_id,
            "duration_ms": duration_ms,
            "error": None,
        }))
        return {
            "statusCode": 202,
            "headers": CORS_HEADERS,
            "body": json.dumps({"payment_intent_id": stripe_intent_id}),
        }

    except PermissionError as exc:
        error_name = type(exc).__name__
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": device_id,
            "action": "dues",
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
            "device_id": device_id,
            "action": "dues",
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
            "device_id": device_id,
            "action": "dues",
            "stripe_payment_intent_id": stripe_intent_id,
            "duration_ms": duration_ms,
            "error": error_name,
        }))
        return error_response(500, "Internal server error")
