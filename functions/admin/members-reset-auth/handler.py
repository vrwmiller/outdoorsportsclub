"""PATCH /v1/admin/members/reset-auth  — Level 6 Webmaster

Resets the specified member's authentication state without modifying any
Cognito identity-provider links. The handler clears social_provider_id in
the members table and calls AdminUserGlobalSignOut so that any active
Cognito sessions are revoked. The member's Cognito account and any linked
social identity providers remain intact; they can sign in again using any
existing authentication method on next login.

Body: { member_id }

Returns:
    200 OK
    400 Bad Request (missing member_id)
    403 Forbidden
    404 Not Found
    500 Internal Server Error
"""
import json
import logging
import os
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

_POOL_ID: str = os.environ["COGNITO_USER_POOL_ID"]


def handler(event: dict, context: Any) -> dict:
    start = time.monotonic()
    actor_member_id: str | None = None
    error_name: str | None = None

    try:
        member = authenticate_member(event)
        actor_member_id = member["member_id"]
        require_level(member, 6)

        body = json.loads(event.get("body") or "{}")
        target_member_id = body.get("member_id")
        if not target_member_id:
            raise ValueError("member_id is required")
        try:
            target_member_id = str(uuid.UUID(str(target_member_id)))
        except (ValueError, TypeError):
            raise ValueError("member_id must be a valid UUID")

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

            # Find the target member to get their social_provider_id and email.
            lookup_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql="SELECT id, email, social_provider_id FROM members WHERE id = :tid",
                parameters=[{"name": "tid", "value": {"stringValue": target_member_id}}],
            )
            if not lookup_result["records"]:
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

            row = lookup_result["records"][0]
            social_provider_id = row[2].get("stringValue") if not row[2].get("isNull") else None

            if social_provider_id:
                # Clear social_provider_id in Aurora.
                rds.execute_statement(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    database=DB_NAME,
                    transactionId=tx["transactionId"],
                    sql="UPDATE members SET social_provider_id = NULL WHERE id = :tid",
                    parameters=[{"name": "tid", "value": {"stringValue": target_member_id}}],
                )

            # Write durable audit record — atomic with the social_provider_id reset.
            rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql=(
                    "INSERT INTO activity_logs (member_id, actor_member_id, activity_type) "
                    "VALUES (:tid, :actor, 'Auth-Reset')"
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

        # Invalidate all Cognito sessions for this user after the DB update commits.
        if social_provider_id:
            cognito = boto3.client("cognito-idp")
            try:
                cognito.admin_user_global_sign_out(
                    UserPoolId=_POOL_ID,
                    Username=social_provider_id,
                )
            except Exception:
                # Cognito sign-out failed after the DB change was committed.
                # Log at ERROR so this is visible in CloudWatch, but still
                # return 200 — the DB state is correct and the caller cannot
                # retry meaningfully (the social_provider_id is already NULL).
                logger.exception(
                    "Cognito sign-out failed during reset-auth [%s]: target_member_id=%s",
                    context.aws_request_id,
                    target_member_id,
                )

        logger.info(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": actor_member_id,
            "device_id": None,
            "action": "admin_members_reset_auth",
            "duration_ms": round((time.monotonic() - start) * 1000),
            "error": None,
        }))

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Auth reset successfully"}),
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
                "action": "admin_members_reset_auth",
                "duration_ms": round((time.monotonic() - start) * 1000),
                "error": error_name,
            }))
