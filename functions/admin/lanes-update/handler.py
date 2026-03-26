"""PATCH /v1/admin/lanes/{lane_id}  — Level 4+ RSO

Updates a lane's configuration or operational status.
Accepted fields: lane_number (renumbering), status (Available | Closed).

A lane with status = 'Occupied' cannot be closed — return 409 Conflict.

Returns:
    200 OK  { lane_id, lane_number, status }
    400 Bad Request (invalid input)
    403 Forbidden
    404 Not Found
    409 Conflict (attempted close of an occupied lane)
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

_ALLOWED_STATUS = {"Available", "Closed"}

# Static map from accepted field name to its parameterised SQL fragment.
# This prevents any client-controlled string from reaching the SQL text.
_COLUMN_CLAUSES: dict[str, str] = {
    "lane_number": "lane_number = :lane_number",
    "status": "status = :status",
}


def handler(event: dict, context: Any) -> dict:
    start = time.monotonic()
    member_id: str | None = None
    error_name: str | None = None

    try:
        member = authenticate_member(event)
        member_id = member["member_id"]
        require_level(member, 4)

        path_params = event.get("pathParameters") or {}
        lane_id = path_params.get("lane_id")
        if not lane_id:
            raise ValueError("lane_id path parameter is required")
        try:
            uuid.UUID(lane_id)
        except ValueError:
            raise ValueError("lane_id must be a valid UUID")

        body = json.loads(event.get("body") or "{}")

        updates: dict = {}
        if "lane_number" in body:
            val = body["lane_number"]
            if not isinstance(val, int) or val < 1:
                raise ValueError("lane_number must be a positive integer")
            if val > 32767:
                raise ValueError("lane_number must not exceed 32767")
            updates["lane_number"] = val
        if "status" in body:
            val = body["status"]
            if val not in _ALLOWED_STATUS:
                raise ValueError(f"status must be one of: {', '.join(sorted(_ALLOWED_STATUS))}")
            updates["status"] = val

        if not updates:
            raise ValueError("No updatable fields provided; accepted fields: lane_number, status")

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

            # Check the lane exists and get current status (lanes not under RLS).
            current_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql="SELECT id, lane_number, status FROM lanes WHERE id = :lid",
                parameters=[{"name": "lid", "value": {"stringValue": lane_id}}],
            )
            if not current_result["records"]:
                rds.commit_transaction(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    transactionId=tx["transactionId"],
                )
                return {
                    "statusCode": 404,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"error": "Lane not found"}),
                }

            current_status = current_result["records"][0][2]["stringValue"]
            if updates.get("status") == "Closed" and current_status == "Occupied":
                rds.commit_transaction(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    transactionId=tx["transactionId"],
                )
                return {
                    "statusCode": 409,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"error": "Cannot close an occupied lane; the occupant must check out first"}),
                }

            set_clauses = []
            params = [{"name": "lid", "value": {"stringValue": lane_id}}]
            for col, val in updates.items():
                set_clauses.append(_COLUMN_CLAUSES[col])
                if isinstance(val, int):
                    params.append({"name": col, "value": {"longValue": val}})
                else:
                    params.append({"name": col, "value": {"stringValue": val}})

            result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql=(
                    f"UPDATE lanes SET {', '.join(set_clauses)} "
                    "WHERE id = :lid RETURNING id, lane_number, status"
                ),
                parameters=params,
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

        row = result["records"][0]
        body_out = {
            "lane_id": row[0]["stringValue"],
            "lane_number": int(row[1]["longValue"]),
            "status": row[2]["stringValue"],
        }

        logger.info(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": None,
            "action": "admin_lanes_update",
            "lane_id": lane_id,
            "updates": updates,
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
    except (ValueError, json.JSONDecodeError) as exc:
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
                "action": "admin_lanes_update",
                "duration_ms": round((time.monotonic() - start) * 1000),
                "error": error_name,
            }))
