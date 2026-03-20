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


def _advance_wait_list(rds: Any, tx_id: str, range_id: str, sns: Any) -> None:
    """Promote the next Waiting entry to Called and optionally send an SMS."""
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
        return  # nothing in queue

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

    # SNS SMS — look up mobile_phone outside the transaction (read-only)
    phone_result = rds.execute_statement(
        resourceArn=DB_CLUSTER_ARN,
        secretArn=DB_SECRET_ARN,
        database=DB_NAME,
        sql="SELECT mobile_phone FROM members WHERE id = :member_id",
        parameters=[{"name": "member_id", "value": {"stringValue": next_member_id}}],
    )
    if phone_result["records"]:
        mobile = phone_result["records"][0][0].get("stringValue")
        if mobile and _SNS_TOPIC_ARN:
            sns.publish(
                TopicArn=_SNS_TOPIC_ARN,
                Message="Your lane is ready. Please check in at the kiosk now.",
                MessageAttributes={
                    "SMSType": {"DataType": "String", "StringValue": "Transactional"},
                    "DefaultSMSDestinationPhoneNumber": {
                        "DataType": "String",
                        "StringValue": mobile,
                    },
                },
            )


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

        # Resolve member
        m_result = rds.execute_statement(
            resourceArn=DB_CLUSTER_ARN,
            secretArn=DB_SECRET_ARN,
            database=DB_NAME,
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
            return {
                "statusCode": 404,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "No active check-in found for this member"}),
            }
        lane_id: str = lane_result["records"][0][0]["stringValue"]

        tx = rds.begin_transaction(
            resourceArn=DB_CLUSTER_ARN, secretArn=DB_SECRET_ARN, database=DB_NAME
        )
        try:
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
            _advance_wait_list(rds, tx["transactionId"], range_id, sns)
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
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Check-out logged"}),
        }

    except LookupError:
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
