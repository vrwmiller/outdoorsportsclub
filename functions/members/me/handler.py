"""GET /v1/members/me

Returns the authenticated member's own profile together with the current
annual dues amount from club_settings so the Member Portal can display it
before the member initiates payment.

Returns:
    200 OK  { member_num, training_level, service_hours, dues_paid_until,
               waiver_signed_at, mobile_phone, annual_dues_cents }
    403 Forbidden (auth failure)
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

        rds = boto3.client("rds-data")
        tx = rds.begin_transaction(
            resourceArn=DB_CLUSTER_ARN, secretArn=DB_SECRET_ARN, database=DB_NAME
        )
        try:
            # Set RLS GUCs: self-access policy matches on members.id.
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

            m_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql=(
                    "SELECT member_num, training_level, service_hours, "
                    "dues_paid_until, waiver_signed_at, mobile_phone "
                    "FROM members WHERE id = :mid"
                ),
                parameters=[{"name": "mid", "value": {"stringValue": member_id}}],
            )
            if not m_result["records"]:
                raise PermissionError("Member not found")

            # club_settings is not under RLS; read directly in the same transaction.
            cs_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql="SELECT annual_dues_cents FROM club_settings LIMIT 1",
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

        row = m_result["records"][0]
        annual_dues_cents = cs_result["records"][0][0]["longValue"] if cs_result["records"] else None

        body = {
            "member_num": row[0]["stringValue"],
            "training_level": int(row[1]["longValue"]),
            "service_hours": (
                str(row[2]["stringValue"]) if "stringValue" in row[2]
                else str(row[2].get("doubleValue", "0"))
            ),
            "dues_paid_until": row[3].get("stringValue") if not row[3].get("isNull") else None,
            "waiver_signed_at": row[4].get("stringValue") if not row[4].get("isNull") else None,
            "mobile_phone": row[5].get("stringValue") if not row[5].get("isNull") else None,
            "annual_dues_cents": annual_dues_cents,
        }

        logger.info(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": None,
            "action": "member_me_get",
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
                "action": "member_me_get",
                "duration_ms": round((time.monotonic() - start) * 1000),
                "error": error_name,
            }))
