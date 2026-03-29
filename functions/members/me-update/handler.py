"""PATCH /v1/members/me

Updates the authenticated member's editable profile fields.
Accepted fields: home_phone, mobile_phone, first_name, last_name,
date_of_birth, street_address, city, state, zip, notification_email,
notify_email, notify_sms, notify_push.

Validation rules:
- home_phone, mobile_phone: E.164 format (e.g. +15551234567)
- state: exactly 2 letters; input is case-insensitive, stored/returned uppercased
- zip: non-empty string when provided (not null-settable via blank string)
- date_of_birth: ISO 8601 date string YYYY-MM-DD
- notification_email: valid email format when non-null
- notify_email, notify_sms, notify_push: boolean values only

Fields absent from the request body are left unchanged (partial update).
member_num, email, training_level, service_hours, dues_paid_until, and
waiver_signed_at are not updatable through this endpoint.

Returns:
    200 OK  { home_phone, mobile_phone, first_name, last_name,
               date_of_birth, street_address, city, state, zip,
               notification_email, notify_email, notify_sms, notify_push }
    400 Bad Request (validation failure or no updatable fields)
    403 Forbidden (auth failure)
    500 Internal Server Error
"""
import json
import logging
import re
import time
from datetime import date
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
# State: exactly 2 ASCII letters (US postal abbreviation).
_STATE_RE = re.compile(r"^[A-Za-z]{2}$")
# Email: permissive but sane — local@domain.tld.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# ISO date: YYYY-MM-DD.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# SEC-20: column names in the SET clause always come from this trusted constant —
# never from request-derived input.
# Text/date columns that accept NULL (value stored as-is or NULL).
_TEXT_COLUMNS = (
    "home_phone",
    "mobile_phone",
    "first_name",
    "last_name",
    "date_of_birth",
    "street_address",
    "city",
    "state",
    "zip",
    "notification_email",
)
# Boolean columns that do NOT accept NULL.
_BOOL_COLUMNS = ("notify_email", "notify_sms", "notify_push")

_ALLOWED_COLUMNS = _TEXT_COLUMNS + _BOOL_COLUMNS


def _validate_e164(value: str) -> str:
    """Return the value if it is a valid E.164 number, else raise ValueError."""
    if not _E164_RE.match(value):
        raise ValueError("Invalid phone number format; expected E.164 (e.g. +15551234567)")
    return value


def _validate_state(value: str) -> str:
    if not _STATE_RE.match(value):
        raise ValueError("state must be exactly 2 letters (e.g. 'CA')")
    return value.upper()


def _validate_zip(value: str) -> str:
    if not value.strip():
        raise ValueError("zip must not be blank")
    return value


def _validate_date(value: str) -> str:
    if not _DATE_RE.match(value):
        raise ValueError("date_of_birth must be a valid YYYY-MM-DD date")
    # Verify it's a real calendar date.
    year, month, day = (int(p) for p in value.split("-"))
    date(year, month, day)  # raises ValueError on invalid date
    return value


def _validate_email(value: str) -> str:
    if not _EMAIL_RE.match(value):
        raise ValueError("notification_email must be a valid email address")
    return value


def handler(event: dict, context: Any) -> dict:
    start = time.monotonic()
    member_id: str | None = None
    error_name: str | None = None

    try:
        member = authenticate_member(event)
        member_id = member["member_id"]

        body = json.loads(event.get("body") or "{}")
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object")

        # Collect only the allowed updatable fields present in the request.
        # Drive the loop from _ALLOWED_COLUMNS so adding a new field here
        # automatically covers body parsing — no second list to keep in sync.
        text_updates: dict[str, str | None] = {}
        bool_updates: dict[str, bool] = {}

        for col in _TEXT_COLUMNS:
            if col not in body:
                continue
            val = body[col]
            if val is None:
                text_updates[col] = None
                continue
            if not isinstance(val, str):
                raise ValueError(f"{col} must be a string")
            if col in ("home_phone", "mobile_phone"):
                val = _validate_e164(val)
            elif col == "state":
                val = _validate_state(val)
            elif col == "zip":
                val = _validate_zip(val)
            elif col == "date_of_birth":
                val = _validate_date(val)
            elif col == "notification_email":
                val = _validate_email(val)
            text_updates[col] = val

        for col in _BOOL_COLUMNS:
            if col not in body:
                continue
            val = body[col]
            if not isinstance(val, bool):
                raise ValueError(f"{col} must be a boolean (true or false)")
            bool_updates[col] = val

        if not text_updates and not bool_updates:
            raise ValueError(
                "No updatable fields provided; accepted fields: " + ", ".join(_ALLOWED_COLUMNS)
            )

        # Build SET clause from a static allowlist — column names are never
        # derived from request input, eliminating the structural SQL-injection
        # risk present when iterating over updates.keys() directly (SEC-20).
        set_clauses = []
        params = [{"name": "mid", "value": {"stringValue": member_id}}]

        for col in _TEXT_COLUMNS:
            if col not in text_updates:
                continue
            set_clauses.append(col + " = :" + col)
            val = text_updates[col]
            if val is None:
                params.append({"name": col, "value": {"isNull": True}})
            else:
                params.append({"name": col, "value": {"stringValue": val}})

        for col in _BOOL_COLUMNS:
            if col not in bool_updates:
                continue
            set_clauses.append(col + " = :" + col)
            params.append({"name": col, "value": {"booleanValue": bool_updates[col]}})

        returning_cols = (
            "home_phone, mobile_phone, first_name, last_name, date_of_birth, "
            "street_address, city, state, zip, notification_email, "
            "notify_email, notify_sms, notify_push"
        )
        update_sql = (
            "UPDATE members SET " + ", ".join(set_clauses) +
            " WHERE id = :mid::uuid"
            " RETURNING " + returning_cols
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
            raise RuntimeError("Member record missing after authenticated update")

        row = result["records"][0]
        # Columns returned in RETURNING order (indices 0-12):
        # 0  home_phone, 1  mobile_phone, 2  first_name, 3  last_name,
        # 4  date_of_birth, 5  street_address, 6  city, 7  state, 8  zip,
        # 9  notification_email, 10 notify_email, 11 notify_sms, 12 notify_push
        def _str(cell: dict) -> str | None:
            return cell.get("stringValue") if not cell.get("isNull") else None

        resp_body = {
            "home_phone": _str(row[0]),
            "mobile_phone": _str(row[1]),
            "first_name": _str(row[2]),
            "last_name": _str(row[3]),
            "date_of_birth": _str(row[4]),
            "street_address": _str(row[5]),
            "city": _str(row[6]),
            "state": _str(row[7]),
            "zip": _str(row[8]),
            "notification_email": _str(row[9]),
            "notify_email": row[10].get("booleanValue", True),
            "notify_sms": row[11].get("booleanValue", False),
            "notify_push": row[12].get("booleanValue", False),
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
