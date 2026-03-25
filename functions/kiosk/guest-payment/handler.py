"""POST /v1/kiosk/guest-payment

Handles the full guest add-on flow for a single guest:
1. Look up or create the guest record
2. Check waiver status (caller must have already invoked POST /v1/kiosk/waiver if needed)
3. Enforce annual visit limit (hard block at 2 — no RSO override)
4. Record payment (Cash recorded directly; NFC/Card via Stripe Terminal)
5. Insert guest_visits row and activity_logs entry inside a serializable transaction

Expected request body:
    {
        "member_num": "<qr_badge_value>",
        "lane_id": "<uuid>",
        "first_name": "<str>",
        "last_name": "<str>",
        "phone": "<E.164>",
        "email": "<str>",
        "payment_method": "Cash" | "NFC" | "Card",
        "stripe_payment_intent_id": "<str>"  # required for NFC/Card; omit for Cash
    }
"""
import json
import logging
import os
import random
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
_stripe_key: str | None = None  # cached on first NFC/Card invocation per container

_VALID_PAYMENT_METHODS = {"Cash", "NFC", "Card"}
_MAX_TX_RETRIES = 3  # max transaction attempts on SQLSTATE 40001 (serialization failure)


def handler(event: dict, context: Any) -> dict:
    start = time.monotonic()
    member_id: str | None = None
    stripe_intent_id: str | None = None
    device_id: str | None = None
    error_name: str | None = None

    try:
        device = authenticate_device(event)
        range_id: str = device["range_id"]
        device_id = device["id"]

        body = json.loads(event.get("body") or "{}")
        member_num: str | None = body.get("member_num")
        lane_id: str | None = body.get("lane_id")
        first_name: str | None = body.get("first_name")
        last_name: str | None = body.get("last_name")
        phone: str | None = body.get("phone")
        email: str | None = body.get("email")
        payment_method: str | None = body.get("payment_method")

        if not all([member_num, lane_id, first_name, last_name, phone, email, payment_method]):
            raise ValueError(
                "Required fields: member_num, lane_id, first_name, last_name, phone, email, payment_method"
            )
        if not isinstance(member_num, str):
            raise ValueError("member_num must be a string")
        if len(member_num) > 64:
            raise ValueError("member_num exceeds maximum length")
        if payment_method not in _VALID_PAYMENT_METHODS:
            raise ValueError(f"payment_method must be one of: {', '.join(_VALID_PAYMENT_METHODS)}")

        stripe_intent_id = body.get("stripe_payment_intent_id")
        if payment_method in ("NFC", "Card") and not stripe_intent_id:
            raise ValueError("stripe_payment_intent_id is required for NFC and Card payments")

        rds = boto3.client("rds-data")

        # Verify Stripe payment before opening any DB transaction (NFC/Card only).
        # Mirrors the pattern in consumable-purchase/handler.py: external network
        # calls must not hold a serializable lock open.
        if payment_method in ("NFC", "Card"):
            if not _STRIPE_SECRET_ARN:
                raise ValueError("Stripe is not configured for this environment")
            fee_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                sql="SELECT guest_fee_cents FROM club_settings WHERE singleton = TRUE",
            )
            if not fee_result["records"]:
                raise RuntimeError("club_settings row missing")
            guest_fee_cents: int = int(fee_result["records"][0][0]["longValue"])
            global _stripe_key
            if _stripe_key is None:
                sm = boto3.client("secretsmanager")
                _stripe_key = sm.get_secret_value(SecretId=_STRIPE_SECRET_ARN)["SecretString"]
            import stripe as _stripe
            _stripe.api_key = _stripe_key
            intent = _stripe.PaymentIntent.retrieve(stripe_intent_id)
            intent_meta = intent.get("metadata") or {}
            intent_ok = (
                intent["status"] == "succeeded"
                and intent["amount"] == guest_fee_cents
                and intent.get("currency", "").lower() == "usd"
                and (intent_meta.get("device_id") is None or str(intent_meta.get("device_id")) == str(device_id))
                and (intent_meta.get("member_num") is None or str(intent_meta.get("member_num")) == str(member_num))
            )
            if not intent_ok:
                duration_ms = int((time.monotonic() - start) * 1000)
                logger.warning(json.dumps({
                    "request_id": context.aws_request_id,
                    "member_id": member_id,
                    "device_id": device_id,
                    "action": "guest_payment",
                    "stripe_payment_intent_id": stripe_intent_id,
                    "duration_ms": duration_ms,
                    "error": "payment_not_confirmed",
                }))
                return {
                    "statusCode": 402,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"error": "Payment not confirmed"}),
                }

        # Retry loop for SQLSTATE 40001 (serialization failure) — max _MAX_TX_RETRIES attempts.
        for _attempt in range(_MAX_TX_RETRIES):
            tx = rds.begin_transaction(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
            )
            try:
                # Set serializable isolation first — must precede any DML or query.
                rds.execute_statement(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    database=DB_NAME,
                    transactionId=tx["transactionId"],
                    sql="SET TRANSACTION ISOLATION LEVEL SERIALIZABLE",
                )

                # Set RLS session variables — kiosk acts with training_level 4 (admin).
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
                    raise PermissionError("Unknown member badge")
                member_id = m_result["records"][0][0]["stringValue"]

                # Set current_member_id GUC — required by policy_guests_member_insert,
                # policy_guest_visits_kiosk_insert, and policy_activity_logs_kiosk_insert.
                rds.execute_statement(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    database=DB_NAME,
                    transactionId=tx["transactionId"],
                    sql="SELECT set_config('app.current_member_id', :mid, true)",
                    parameters=[{"name": "mid", "value": {"stringValue": member_id}}],
                )

                # Verify lane belongs to this range and is occupied by this member
                lane_check = rds.execute_statement(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    database=DB_NAME,
                    transactionId=tx["transactionId"],
                    sql=(
                        "SELECT id FROM lanes "
                        "WHERE id = :lane_id AND range_id = :range_id "
                        "AND current_member_id = :member_id AND status = 'Occupied'"
                    ),
                    parameters=[
                        {"name": "lane_id", "value": {"stringValue": lane_id}},
                        {"name": "range_id", "value": {"stringValue": range_id}},
                        {"name": "member_id", "value": {"stringValue": member_id}},
                    ],
                )
                if not lane_check["records"]:
                    raise PermissionError("Lane not found or not occupied by this member on this range")

                # UPSERT guest — eliminates the SELECT+INSERT race condition against the unique constraint.
                g_result = rds.execute_statement(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    database=DB_NAME,
                    transactionId=tx["transactionId"],
                    sql=(
                        "INSERT INTO guests (id, first_name, last_name, phone, email) "
                        "VALUES (gen_random_uuid(), :first_name, :last_name, :phone, :email) "
                        "ON CONFLICT ON CONSTRAINT uq_guests_identity "
                        "DO UPDATE SET id = guests.id "
                        "RETURNING id, waiver_signed_at"
                    ),
                    parameters=[
                        {"name": "first_name", "value": {"stringValue": first_name}},
                        {"name": "last_name", "value": {"stringValue": last_name}},
                        {"name": "phone", "value": {"stringValue": phone}},
                        {"name": "email", "value": {"stringValue": email}},
                    ],
                )
                guest_id: str = g_result["records"][0][0]["stringValue"]
                waiver_signed_at = g_result["records"][0][1].get("stringValue")

                # Check waiver validity (1-year expiration)
                import datetime
                if waiver_signed_at:
                    signed_date = datetime.datetime.fromisoformat(
                        waiver_signed_at.rstrip("Z")
                    ).replace(tzinfo=datetime.timezone.utc)
                    one_year_ago = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=365)
                    waiver_valid = signed_date >= one_year_ago
                else:
                    waiver_valid = False

                if not waiver_valid:
                    # Caller should invoke POST /v1/kiosk/waiver first — return 400 with context
                    raise ValueError("Guest waiver is missing or expired; capture signature first")

                # Annual visit limit check — transaction is serializable (set above).
                count_result = rds.execute_statement(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    database=DB_NAME,
                    transactionId=tx["transactionId"],
                    sql=(
                        "SELECT COUNT(*) FROM guest_visits "
                        "WHERE guest_id = :guest_id AND member_id = :member_id "
                        "AND visited_at >= date_trunc('year', now() AT TIME ZONE 'UTC') "
                        "AND visited_at < date_trunc('year', now() AT TIME ZONE 'UTC') + INTERVAL '1 year'"
                    ),
                    parameters=[
                        {"name": "guest_id", "value": {"stringValue": guest_id}},
                        {"name": "member_id", "value": {"stringValue": member_id}},
                    ],
                )
                visit_count: int = int(count_result["records"][0][0]["longValue"])
                if visit_count >= 2:
                    rds.rollback_transaction(
                        resourceArn=DB_CLUSTER_ARN,
                        secretArn=DB_SECRET_ARN,
                        transactionId=tx["transactionId"],
                    )
                    duration_ms = int((time.monotonic() - start) * 1000)
                    logger.warning(json.dumps({
                        "request_id": context.aws_request_id,
                        "member_id": member_id,
                        "device_id": device_id,
                        "action": "guest_payment",
                        "stripe_payment_intent_id": stripe_intent_id,
                        "duration_ms": duration_ms,
                        "error": "annual_limit_reached",
                    }))
                    return {
                        "statusCode": 403,
                        "headers": CORS_HEADERS,
                        "body": json.dumps({"error": "Annual guest visit limit reached"}),
                    }

                # Insert guest_visits and activity_log
                rds.execute_statement(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    database=DB_NAME,
                    transactionId=tx["transactionId"],
                    sql=(
                        "INSERT INTO guest_visits "
                        "(id, guest_id, member_id, range_id, lane_id, visited_at, "
                        "stripe_payment_intent_id, payment_method) "
                        "VALUES (gen_random_uuid(), :guest_id, :member_id, :range_id, :lane_id, "
                        "now(), :stripe_intent, :payment_method)"
                    ),
                    parameters=[
                        {"name": "guest_id", "value": {"stringValue": guest_id}},
                        {"name": "member_id", "value": {"stringValue": member_id}},
                        {"name": "range_id", "value": {"stringValue": range_id}},
                        {"name": "lane_id", "value": {"stringValue": lane_id}},
                        {"name": "stripe_intent", "value": (
                            {"stringValue": stripe_intent_id} if stripe_intent_id
                            else {"isNull": True}
                        )},
                        {"name": "payment_method", "value": {"stringValue": payment_method}},
                    ],
                )
                rds.execute_statement(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    database=DB_NAME,
                    transactionId=tx["transactionId"],
                    sql=(
                        "INSERT INTO activity_logs "
                        "(member_id, device_id, lane_id, guest_id, activity_type, "
                        "stripe_payment_intent_id, payment_method, timestamp) "
                        "VALUES (:member_id, :device_id, :lane_id, :guest_id, 'Guest-Payment', "
                        ":stripe_intent, :payment_method, now())"
                    ),
                    parameters=[
                        {"name": "member_id", "value": {"stringValue": member_id}},
                        {"name": "device_id", "value": {"stringValue": device_id}},
                        {"name": "lane_id", "value": {"stringValue": lane_id}},
                        {"name": "guest_id", "value": {"stringValue": guest_id}},
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
                break  # commit succeeded — exit retry loop
            except Exception as _tx_exc:
                rds.rollback_transaction(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    transactionId=tx["transactionId"],
                )
                _msg = str(_tx_exc)
                if "40001" in _msg or "could not serialize" in _msg.lower():
                    if _attempt < _MAX_TX_RETRIES - 1:
                        time.sleep(0.1 * (2 ** _attempt) + random.uniform(0, 0.05))
                    continue
                raise
        else:
            # All _MAX_TX_RETRIES attempts failed due to serialization failure.
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.error(json.dumps({
                "request_id": context.aws_request_id,
                "member_id": member_id,
                "device_id": device_id,
                "action": "guest_payment",
                "stripe_payment_intent_id": stripe_intent_id,
                "duration_ms": duration_ms,
                "error": "serialization_failure_exhausted",
            }))
            return error_response(503, "Service temporarily unavailable, please retry")

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": device_id,
            "action": "guest_payment",
            "stripe_payment_intent_id": stripe_intent_id,
            "duration_ms": duration_ms,
            "error": None,
        }))
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Guest payment recorded"}),
        }

    except PermissionError as exc:
        error_name = type(exc).__name__
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": device_id,
            "action": "guest_payment",
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
            "action": "guest_payment",
            "stripe_payment_intent_id": stripe_intent_id,
            "duration_ms": duration_ms,
            "error": error_name,
        }))
        return error_response(400, str(exc))
    except Exception as exc:  # noqa: BLE001
        error_name = type(exc).__name__
        duration_ms = int((time.monotonic() - start) * 1000)
        if (
            "duplicate key value violates unique constraint" in str(exc)
            and "idx_guest_visits_stripe_payment_intent_id" in str(exc)
        ):
            logger.warning(json.dumps({
                "request_id": context.aws_request_id,
                "member_id": member_id,
                "device_id": device_id,
                "action": "guest_payment",
                "stripe_payment_intent_id": stripe_intent_id,
                "duration_ms": duration_ms,
                "error": error_name,
                "error_code": "duplicate_payment_intent",
            }))
            return error_response(409, "Payment intent already processed")
        logger.exception(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": device_id,
            "action": "guest_payment",
            "stripe_payment_intent_id": stripe_intent_id,
            "duration_ms": duration_ms,
            "error": error_name,
        }))
        return error_response(500, "Internal server error")
