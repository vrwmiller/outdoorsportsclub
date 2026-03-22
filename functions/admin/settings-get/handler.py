"""GET /v1/admin/settings  — Level 5+ Administrator

Returns the current club_settings row.

Returns:
    200 OK  { annual_dues_cents, updated_at, updated_by_member_id }
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
                    "SELECT annual_dues_cents, updated_at, updated_by_member_id "
                    "FROM club_settings LIMIT 1"
                ),
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
        body = {
            "annual_dues_cents": int(row[0]["longValue"]),
            "updated_at": row[1].get("stringValue") if not row[1].get("isNull") else None,
            "updated_by_member_id": row[2].get("stringValue") if not row[2].get("isNull") else None,
        }

        logger.info(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": None,
            "action": "admin_settings_get",
            "duration_ms": round((time.monotonic() - start) * 1000),
            "error": None,
        }))

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(body),
        }

    except PermissionError as exc:
        error_name = type(exc).__name__
        logger.warning("Auth failure [%s]: %s", context.aws_request_id, exc)
        return error_response(403, "Forbidden")
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
                "action": "admin_settings_get",
                "duration_ms": round((time.monotonic() - start) * 1000),
                "error": error_name,
            }))
