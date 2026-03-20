"""POST /v1/kiosk/check-out

Clears the member's lane, writes a Range-Checkout activity log entry,
and advances the wait list (with SNS SMS if mobile_phone is set).

Expected request body:
    { "member_num": "<qr_badge_value>" }
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

_SNS_TOPIC_ARN: str = os.environ.get("SNS_ALERTS_TOPIC_ARN", "")


def _advance_wait_list(rds: Any, tx_id: str, range_id: str) -> str | None:
    """Promote the next Waiting entry to Called; return mobile_phone to notify (or None).

    The caller must publish the SMS *after* committing the transaction to avoid
    notifying a member when the DB write ultimately fails.
    """
    next_result = rds.execute_statement(
        resourceArn=DB_CLUSTER_ARN,
        secretArn=DB_SECRET_ARN,
        database=DB_NAME,
        transactionId=tx_id,
        sql=(
            "SELECT id, member_id FROM wait_list "
            "WHERE range_id = :range_id AND status = 'Waiting' "
            "ORDER BY position LIMIT 1"
        ),
        parameters=[{"name": "range_id", "value": {"stringValue": range_id}}],
    )
    if not next_result["records"]:
        return None  # nothing in queue

    entry_id = next_result["records"][0][0]["stringValue"]
    next_member_id = next_result["records"][0][1]["stringValue"]

    rds.execute_statement(
        resourceArn=DB_CLUSTER_ARN,
        secretArn=DB_SECRET_ARN,
        database=DB_NAME,
        transactionId=tx_id,
        sql=(
            "UPDATE wait_list "
            "SET status = 'Called', called_at = now(), "
            "expires_at = now() + INTERVAL '5 minutes' "
            "WHERE id = :entry_id"
        ),
        parameters=[{"name": "entry_id", "value": {"stringValue": entry_id}}],
    )

    # Look up mobile_phone to return for post-commit SMS.
    # Must run inside the same transaction so the RLS session var is still set.
    phone_result = rds.execute_statement(
        resourceArn=DB_CLUSTER_ARN,
        secretArn=DB_SECRET_ARN,
        database=DB_NAME,
        transactionId=tx_id,
        sql="SELECT mobile_phone FROM members WHERE id = :member_id",
        parameters=[{"name": "member_id", "value": {"stringValue": next_member_id}}],
    )
    if phone_result["records"]:
        return phone_result["records"][0][0].get("stringValue")
    return None


def handler(event: dict, context: Any) -> dict:
    start = time.monotonic()
    member_id: str | None = None
    error_name: str | None = None

    try:
        device = authenticate_device(event)
        range_id: str = device["range_id"]
        device_id: str = device["id"]

        body = json.loads(event.get("body") or "{}")
        member_num: str | None = body.get("member_num")
        if not member_num:
            raise ValueError("member_num is required")

        rds = boto3.client("rds-data")
        sns = boto3.client("sns")

        notify_phone: str | None = None
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
                parameters=[
                    {"name": "member_num", "value": {"stringValue": member_num}}
                ],
            )
            if not m_result["records"]:
                raise LookupError("Unknown member badge")
            member_id = m_result["records"][0][0]["stringValue"]

            # Find the lane this member currently occupies on this range
            lane_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql=(
                    "SELECT id FROM lanes "
                    "WHERE current_member_id = :member_id AND range_id = :range_id "
                    "AND status = 'Occupied'"
                ),
                parameters=[
                    {"name": "member_id", "value": {"stringValue": member_id}},
                    {"name": "range_id", "value": {"stringValue": range_id}},
                ],
            )
            if not lane_result["records"]:
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
                    "action": "checkout",
                    "duration_ms": duration_ms,
                    "error": "no_active_checkin",
                }))
                return {
                    "statusCode": 404,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"error": "No active check-in found for this member"}),
                }
            lane_id: str = lane_result["records"][0][0]["stringValue"]

            rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql=(
                    "UPDATE lanes SET status = 'Available', "
                    "current_member_id = NULL, guest_count = 0, checked_in_at = NULL "
                    "WHERE id = :lane_id"
                ),
                parameters=[{"name": "lane_id", "value": {"stringValue": lane_id}}],
            )
            rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql=(
                    "INSERT INTO activity_logs "
                    "(member_id, device_id, lane_id, activity_type, timestamp) "
                    "VALUES (:member_id, :device_id, :lane_id, 'Range-Checkout', now())"
                ),
                parameters=[
                    {"name": "member_id", "value": {"stringValue": member_id}},
                    {"name": "device_id", "value": {"stringValue": device_id}},
                    {"name": "lane_id", "value": {"stringValue": lane_id}},
                ],
            )
            notify_phone = _advance_wait_list(rds, tx["transactionId"], range_id)
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
            "action": "checkout",
            "duration_ms": duration_ms,
            "error": None,
        }))
        # Send SMS after commit — direct SMS to avoid leaking phone number to topic subscribers
        if notify_phone and _SNS_TOPIC_ARN:
            sns.publish(
                PhoneNumber=notify_phone,
                Message="Your lane is ready. Please check in at the kiosk now.",
                MessageAttributes={
                    "AWS.SNS.SMS.SMSType": {"DataType": "String", "StringValue": "Transactional"},
                },
            )
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Check-out logged"}),
        }

    except LookupError:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": None,
            "action": "checkout",
            "duration_ms": duration_ms,
            "error": "LookupError",
        }))
        return {
            "statusCode": 404,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Not found"}),
        }
    except PermissionError as exc:
        error_name = type(exc).__name__
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": None,
            "action": "checkout",
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
            "action": "checkout",
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
            "action": "checkout",
            "duration_ms": duration_ms,
            "error": error_name,
        }))
        return error_response(500, "Internal server error")
