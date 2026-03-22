"""PATCH /v1/members/me

Updates the authenticated member's editable profile fields.
Accepted fields: home_phone, mobile_phone.

mobile_phone is validated and normalised to E.164 before storage.
Fields absent from the request body are left unchanged.
member_num, email, training_level, service_hours, dues_paid_until, and
waiver_signed_at are not updatable through this endpoint.

Returns:
    200 OK  { home_phone, mobile_phone }
    400 Bad Request (invalid phone format or no updatable fields)
    403 Forbidden (auth failure)
    500 Internal Server Error
"""
import json
import logging
import re
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

# E.164: + followed by 1-3 digit country code + subscriber number; total 7-15 digits.
_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")


def _validate_e164(value: str) -> str:
    """Return the value if it is a valid E.164 number, else raise ValueError."""
    if not _E164_RE.match(value):
        raise ValueError(f"Invalid phone number format; expected E.164 (e.g. +15551234567): {value!r}")
    return value


def handler(event: dict, context: Any) -> dict:
    start = time.monotonic()
    member_id: str | None = None
    error_name: str | None = None

    try:
        member = authenticate_member(event)
        member_id = member["member_id"]

        body = json.loads(event.get("body") or "{}")

        # Collect only the allowed updatable fields present in the request.
        updates: dict[str, str | None] = {}

        if "home_phone" in body:
            val = body["home_phone"]
            if val is not None:
                _validate_e164(str(val))
            updates["home_phone"] = val  # None means set to NULL

        if "mobile_phone" in body:
            val = body["mobile_phone"]
            if val is not None:
                _validate_e164(str(val))
            updates["mobile_phone"] = val

        if not updates:
            raise ValueError("No updatable fields provided; accepted fields: home_phone, mobile_phone")

        # Build dynamic SET clause — only update supplied fields.
        set_clauses = []
        params = [{"name": "mid", "value": {"stringValue": member_id}}]
        for col, val in updates.items():
            set_clauses.append(f"{col} = :{col}")
            if val is None:
                params.append({"name": col, "value": {"isNull": True}})
            else:
                params.append({"name": col, "value": {"stringValue": val}})

        update_sql = (
            f"UPDATE members SET {', '.join(set_clauses)} "
            "WHERE id = :mid "
            "RETURNING home_phone, mobile_phone"
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

            result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql=update_sql,
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

        if not result["records"]:
            raise PermissionError("Member not found")

        row = result["records"][0]
        resp_body = {
            "home_phone": row[0].get("stringValue") if not row[0].get("isNull") else None,
            "mobile_phone": row[1].get("stringValue") if not row[1].get("isNull") else None,
        }

        logger.info(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": None,
            "action": "member_me_patch",
            "duration_ms": round((time.monotonic() - start) * 1000),
            "error": None,
        }))

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(resp_body),
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
                "action": "member_me_patch",
                "duration_ms": round((time.monotonic() - start) * 1000),
                "error": error_name,
            }))
