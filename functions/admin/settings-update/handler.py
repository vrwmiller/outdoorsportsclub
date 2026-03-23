"""PATCH /v1/admin/settings  — Level 5+ Administrator

Updates one or more fields in the club_settings row.
Accepted fields: annual_dues_cents.

Sets updated_at = NOW() and updated_by_member_id to the Administrator's
members.id. Does not affect in-flight Stripe Payment Intents.

Body: { annual_dues_cents: positive integer }

Returns:
    200 OK  { annual_dues_cents, updated_at }
    400 Bad Request (negative or zero amount)
    403 Forbidden
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
    member_id: str | None = None
    error_name: str | None = None

    try:
        member = authenticate_member(event)
        member_id = member["member_id"]
        require_level(member, 5)

        _MAX_DUES_CENTS = 99_999  # $999.99

        body = json.loads(event.get("body") or "{}")
        annual_dues_cents = body.get("annual_dues_cents")
        if annual_dues_cents is None:
            raise ValueError("annual_dues_cents is required")
        if not isinstance(annual_dues_cents, int) or annual_dues_cents <= 0:
            raise ValueError("annual_dues_cents must be a positive integer")
        if annual_dues_cents > _MAX_DUES_CENTS:
            raise ValueError(f"annual_dues_cents exceeds maximum ({_MAX_DUES_CENTS})")

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

            # club_settings is not under RLS.
            result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql=(
                    "UPDATE club_settings "
                    "SET annual_dues_cents = :cents, "
                    "    updated_at = NOW(), "
                    "    updated_by_member_id = :mid "
                    "WHERE singleton = TRUE "
                    "RETURNING annual_dues_cents, updated_at"
                ),
                parameters=[
                    {"name": "cents", "value": {"longValue": annual_dues_cents}},
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
            raise Exception("club_settings row not found — database may not be seeded")

        row = result["records"][0]
        body_out = {
            "annual_dues_cents": int(row[0]["longValue"]),
            "updated_at": row[1].get("stringValue") if not row[1].get("isNull") else None,
        }

        logger.info(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": None,
            "action": "admin_settings_update",
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
                "action": "admin_settings_update",
                "duration_ms": round((time.monotonic() - start) * 1000),
                "error": error_name,
            }))
