"""PATCH /v1/admin/members/{member_id}/level  — Level 5+ Administrator

Updates members.training_level for the specified member. Writes a Level-Change
entry to activity_logs with actor_member_id = the Administrator's members.id.

Body: { training_level: 0-6 }

Returns:
    200 OK  { member_id, training_level }
    400 Bad Request (missing or out-of-range training_level)
    403 Forbidden
    404 Not Found
    500 Internal Server Error
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

        body = json.loads(event.get("body") or "{}")
        new_level = body.get("training_level")
        if new_level is None:
            raise ValueError("training_level is required")
        if not isinstance(new_level, int) or new_level < 0 or new_level > 6:
            raise ValueError("training_level must be an integer between 0 and 6")
        # Privilege escalation guard: an actor may only grant levels strictly below
        # their own Aurora-queried training_level (never equal or higher).
        if new_level >= member["training_level"]:
            raise PermissionError(
                "Cannot grant a training_level equal to or higher than your own"
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

            # Verify target member exists and fetch their current level.
            check_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql="SELECT id, training_level FROM members WHERE id = :tid",
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

            target_current_level = check_result["records"][0][1]["longValue"]
            if target_current_level >= member["training_level"]:
                rds.commit_transaction(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    transactionId=tx["transactionId"],
                )
                return {
                    "statusCode": 403,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({
                        "error": (
                            "Cannot modify a member whose training_level"
                            " is at or above your own"
                        )
                    }),
                }

            rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql="UPDATE members SET training_level = :new_level WHERE id = :tid",
                parameters=[
                    {"name": "new_level", "value": {"longValue": new_level}},
                    {"name": "tid", "value": {"stringValue": target_member_id}},
                ],
            )

            # Audit log — Level-Change.
            rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql=(
                    "INSERT INTO activity_logs (member_id, actor_member_id, activity_type) "
                    "VALUES (:tid, :actor, 'Level-Change')"
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

        logger.info(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": actor_member_id,
            "device_id": None,
            "action": "admin_members_level",
            "training_level": new_level,
            "duration_ms": round((time.monotonic() - start) * 1000),
            "error": None,
        }))

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"member_id": target_member_id, "training_level": new_level}),
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
                "member_id": actor_member_id,
                "device_id": None,
                "action": "admin_members_level",
                "duration_ms": round((time.monotonic() - start) * 1000),
                "error": error_name,
            }))
