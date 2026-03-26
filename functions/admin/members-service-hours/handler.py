"""PATCH /v1/admin/members/{member_id}/service-hours  — Level 5+ Administrator

Sets members.service_hours to the supplied value. Writes a Service-Hours-Update
entry to activity_logs with actor_member_id = the Administrator's members.id.

Body: { service_hours: non-negative number }

Returns:
    200 OK  { service_hours }
    400 Bad Request (missing or negative value)
    403 Forbidden
    404 Not Found
    500 Internal Server Error
"""
import json
import logging
import math
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
    actor_member_id: str | None = None
    error_name: str | None = None

    try:
        member = authenticate_member(event)
        actor_member_id = member["member_id"]
        require_level(member, 5)

        path_params = event.get("pathParameters") or {}
        target_member_id = path_params.get("member_id")
        if not target_member_id:
            raise ValueError("member_id path parameter is required")
        try:
            uuid.UUID(target_member_id)
        except ValueError:
            raise ValueError("member_id must be a valid UUID")

        body = json.loads(event.get("body") or "{}")
        service_hours = body.get("service_hours")
        if service_hours is None:
            raise ValueError("service_hours is required")
        if (
            isinstance(service_hours, bool)
            or not isinstance(service_hours, (int, float))
            or service_hours < 0
            or service_hours > 999.99
            or not math.isfinite(float(service_hours))
        ):
            raise ValueError(
                "service_hours must be a non-negative finite number no greater than 999.99"
            )

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
                parameters=[{"name": "mid", "value": {"stringValue": actor_member_id}}],
            )
            rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql="SELECT set_config('app.current_training_level', :level, true)",
                parameters=[{"name": "level", "value": {"stringValue": str(member["training_level"])}}],
            )

            check_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql="SELECT id FROM members WHERE id = :tid",
                parameters=[{"name": "tid", "value": {"stringValue": target_member_id}}],
            )
            if not check_result["records"]:
                rds.commit_transaction(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    transactionId=tx["transactionId"],
                )
                return {
                    "statusCode": 404,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"error": "Member not found"}),
                }

            update_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql="UPDATE members SET service_hours = :hours WHERE id = :tid RETURNING service_hours",
                parameters=[
                    {"name": "hours", "value": {"doubleValue": float(service_hours)}},
                    {"name": "tid", "value": {"stringValue": target_member_id}},
                ],
            )
            if not update_result["records"]:
                rds.rollback_transaction(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    transactionId=tx["transactionId"],
                )
                return {
                    "statusCode": 404,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"error": "Member not found"}),
                }

            rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql=(
                    "INSERT INTO activity_logs (member_id, actor_member_id, activity_type) "
                    "VALUES (:tid, :actor, 'Service-Hours-Update')"
                ),
                parameters=[
                    {"name": "tid", "value": {"stringValue": target_member_id}},
                    {"name": "actor", "value": {"stringValue": actor_member_id}},
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

        stored_hours = update_result["records"][0][0]
        hours_out = stored_hours.get("stringValue") or str(stored_hours.get("doubleValue", service_hours))

        logger.info(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": actor_member_id,
            "device_id": None,
            "action": "admin_members_service_hours",
            "target_member_id": target_member_id,
            "new_service_hours": hours_out,
            "duration_ms": round((time.monotonic() - start) * 1000),
            "error": None,
        }))

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"service_hours": hours_out}),
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
                "member_id": actor_member_id,
                "device_id": None,
                "action": "admin_members_service_hours",
                "duration_ms": round((time.monotonic() - start) * 1000),
                "error": error_name,
            }))
