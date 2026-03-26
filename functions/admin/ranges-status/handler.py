"""PATCH /v1/admin/ranges/{range_id}/status  — Level 4+ RSO

Sets ranges.is_open to true or false. Closing is always a soft operation;
lane occupancy is preserved exactly as it is at closure time.

Body: { is_open: bool }

Returns:
    200 OK  { range_id, is_open }
    400 Bad Request (missing or invalid is_open)
    403 Forbidden
    404 Not Found
    500 Internal Server Error
"""
import json
import logging
import time
import uuid
from typing import Any

import boto3

from _auth import (
    DB_CLUSTER_ARN,
    DB_SECRET_ARN,
    DB_NAME,
    CORS_HEADERS,
    authenticate_member,
    require_level,
    error_response,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: dict, context: Any) -> dict:
    start = time.monotonic()
    member_id: str | None = None
    error_name: str | None = None

    try:
        member = authenticate_member(event)
        member_id = member["member_id"]
        require_level(member, 4)

        path_params = event.get("pathParameters") or {}
        range_id = path_params.get("range_id")
        if not range_id:
            raise ValueError("range_id path parameter is required")
        try:
            uuid.UUID(range_id)
        except ValueError:
            raise ValueError("range_id must be a valid UUID")

        body = json.loads(event.get("body") or "{}")
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object")
        if "is_open" not in body:
            raise ValueError("is_open is required")
        is_open = body["is_open"]
        if not isinstance(is_open, bool):
            raise ValueError("is_open must be a boolean")

        rds = boto3.client("rds-data")
        tx = rds.begin_transaction(
            resourceArn=DB_CLUSTER_ARN, secretArn=DB_SECRET_ARN, database=DB_NAME
        )
        try:
            rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql="SELECT set_config('app.current_member_id', :mid, true)",
                parameters=[{"name": "mid", "value": {"stringValue": member_id}}],
            )
            rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql="SELECT set_config('app.current_training_level', :level, true)",
                parameters=[{"name": "level", "value": {"stringValue": str(member["training_level"])}}],
            )

            # ranges not under RLS.
            result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql=(
                    "UPDATE ranges SET is_open = :is_open WHERE id = :rid "
                    "RETURNING id, is_open"
                ),
                parameters=[
                    {"name": "is_open", "value": {"booleanValue": is_open}},
                    {"name": "rid", "value": {"stringValue": range_id}},
                ],
            )
            if result["records"]:
                rds.execute_statement(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    database=DB_NAME,
                    transactionId=tx["transactionId"],
                    sql=(
                        "INSERT INTO activity_logs (member_id, actor_member_id, activity_type) "
                        "VALUES (:mid, :mid, 'Range-Status-Change')"
                    ),
                    parameters=[
                        {"name": "mid", "value": {"stringValue": member_id}},
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

        if not result["records"]:
            return {
                "statusCode": 404,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Range not found"}),
            }

        row = result["records"][0]
        body_out = {
            "range_id": row[0]["stringValue"],
            "is_open": row[1]["booleanValue"],
        }

        logger.info(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": None,
            "action": "admin_ranges_status",
            "range_id": range_id,
            "is_open": is_open,
            "duration_ms": round((time.monotonic() - start) * 1000),
            "error": None,
        }))

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(body_out),
        }

    except PermissionError as exc:
        error_name = type(exc).__name__
        logger.warning("Auth failure [%s]: %s", context.aws_request_id, exc)
        return error_response(403, "Forbidden")
    except json.JSONDecodeError:
        error_name = "JSONDecodeError"
        logger.warning("Validation error [%s]: invalid JSON body", context.aws_request_id)
        return error_response(400, "Invalid JSON body")
    except ValueError as exc:
        error_name = type(exc).__name__
        logger.warning("Validation error [%s]: %s", context.aws_request_id, exc)
        return error_response(400, str(exc))
    except Exception as exc:
        error_name = type(exc).__name__
        logger.exception("Unhandled error [%s]: %s", context.aws_request_id, exc)
        return error_response(500, "Internal server error")
    finally:
        if error_name:
            logger.info(json.dumps({
                "request_id": context.aws_request_id,
                "member_id": member_id,
                "device_id": None,
                "action": "admin_ranges_status",
                "duration_ms": round((time.monotonic() - start) * 1000),
                "error": error_name,
            }))
