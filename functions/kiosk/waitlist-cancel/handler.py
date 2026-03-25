"""DELETE /v1/kiosk/wait-list/{entry_id}

Cancels the calling member's active wait_list entry for this range.
Sets status = Cancelled and recalculates position for remaining Waiting entries.

Path parameter: entry_id (from event["pathParameters"]["entry_id"])
Request body must include: { "member_num": "<qr_badge_value>" }
"""
import json
import logging
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


def handler(event: dict, context: Any) -> dict:
    start = time.monotonic()
    member_id: str | None = None
    device_id: str | None = None
    error_name: str | None = None

    try:
        device = authenticate_device(event)
        range_id: str = device["range_id"]
        device_id = device["id"]

        path_params = event.get("pathParameters") or {}
        entry_id: str | None = path_params.get("entry_id")
        if not entry_id:
            raise ValueError("entry_id path parameter is required")

        body = json.loads(event.get("body") or "{}")
        member_num: str | None = body.get("member_num")
        if not member_num:
            raise ValueError("member_num is required")
        if not isinstance(member_num, str):
            raise ValueError("member_num must be a string")
        if len(member_num) > 64:
            raise ValueError("member_num exceeds maximum length")

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
                raise LookupError("Unknown member badge")
            member_id = m_result["records"][0][0]["stringValue"]

            # Fetch the entry — must belong to this member on this range
            entry_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql=(
                    "SELECT id, position FROM wait_list "
                    "WHERE id = :entry_id AND member_id = :member_id "
                    "AND range_id = :range_id AND status IN ('Waiting', 'Called')"
                ),
                parameters=[
                    {"name": "entry_id", "value": {"stringValue": entry_id}},
                    {"name": "member_id", "value": {"stringValue": member_id}},
                    {"name": "range_id", "value": {"stringValue": range_id}},
                ],
            )
            if not entry_result["records"]:
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
                    "action": "waitlist_cancel",
                    "duration_ms": duration_ms,
                    "error": "entry_not_found",
                }))
                return {
                    "statusCode": 404,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"error": "Wait list entry not found"}),
                }
            cancelled_position: int = int(entry_result["records"][0][1]["longValue"])

            cancel_update = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql=(
                    "UPDATE wait_list SET status = 'Cancelled' "
                    "WHERE id = :entry_id AND member_id = :member_id "
                    "AND range_id = :range_id AND status IN ('Waiting', 'Called')"
                ),
                parameters=[
                    {"name": "entry_id", "value": {"stringValue": entry_id}},
                    {"name": "member_id", "value": {"stringValue": member_id}},
                    {"name": "range_id", "value": {"stringValue": range_id}},
                ],
            )
            if cancel_update.get("numberOfRecordsUpdated", 0) == 0:
                raise ValueError("Wait list entry could not be cancelled (status may have changed)")
            # Recalculate positions for entries behind the cancelled one
            rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql=(
                    "UPDATE wait_list SET position = position - 1 "
                    "WHERE range_id = :range_id AND status = 'Waiting' "
                    "AND position > :cancelled_position"
                ),
                parameters=[
                    {"name": "range_id", "value": {"stringValue": range_id}},
                    {"name": "cancelled_position", "value": {"longValue": cancelled_position}},
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
            "action": "waitlist_cancel",
            "duration_ms": duration_ms,
            "error": None,
        }))
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Wait list entry cancelled"}),
        }

    except LookupError:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": device_id,
            "action": "waitlist_cancel",
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
            "device_id": device_id,
            "action": "waitlist_cancel",
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
            "action": "waitlist_cancel",
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
            "action": "waitlist_cancel",
            "duration_ms": duration_ms,
            "error": error_name,
        }))
        return error_response(500, "Internal server error")
