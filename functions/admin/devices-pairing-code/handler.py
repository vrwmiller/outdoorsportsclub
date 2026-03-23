"""POST /v1/admin/devices/pairing-code  — Level 6 Webmaster

Creates a new device row in devices (status Pending-Pairing) with a
cryptographically random alphanumeric pairing code and a 15-minute expiry.

A device row with an unexpired pairing code for the same location_tag is
rejected to prevent duplicate device creation.

Body: { location_tag, range_id }

Returns:
    201 Created  { device_id, pairing_code, expires_at }
    400 Bad Request (missing fields)
    403 Forbidden
    409 Conflict (unexpired code already exists for location_tag)
    500 Internal Server Error
"""
import hashlib
import hmac
import json
import logging
import os
import secrets
import string
import time
from datetime import datetime, timezone, timedelta
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

# ---------------------------------------------------------------------------
# Cold-start: load HMAC salt for pairing-code hashing.
# ---------------------------------------------------------------------------

if not os.environ.get("DEVICE_TOKEN_SALT_ARN"):
    raise RuntimeError("Missing required environment variable: DEVICE_TOKEN_SALT_ARN")

_sm = boto3.client("secretsmanager")
_raw_salt: str = _sm.get_secret_value(
    SecretId=os.environ["DEVICE_TOKEN_SALT_ARN"]
)["SecretString"]
try:
    _DEVICE_TOKEN_SALT: str = json.loads(_raw_salt)["salt"]
except (json.JSONDecodeError, KeyError) as _exc:
    raise RuntimeError(
        "DEVICE_TOKEN_SALT secret must be JSON with a 'salt' field"
    ) from _exc


def _hash_pairing_code(code: str) -> str:
    """Return HMAC-SHA256 hex digest of the pairing code."""
    return hmac.new(_DEVICE_TOKEN_SALT.encode(), code.encode(), hashlib.sha256).hexdigest()


_CODE_ALPHABET = string.ascii_uppercase + string.digits
_CODE_LENGTH = 8
_EXPIRY_MINUTES = 15


def _generate_pairing_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


def handler(event: dict, context: Any) -> dict:
    start = time.monotonic()
    member_id: str | None = None
    error_name: str | None = None

    try:
        member = authenticate_member(event)
        member_id = member["member_id"]
        require_level(member, 6)

        body = json.loads(event.get("body") or "{}")
        location_tag = body.get("location_tag")
        range_id = body.get("range_id")
        if not location_tag:
            raise ValueError("location_tag is required")
        if not range_id:
            raise ValueError("range_id is required")

        pairing_code = _generate_pairing_code()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=_EXPIRY_MINUTES)
        expires_at_str = expires_at.isoformat()

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

            # Check for an unexpired code on this location_tag.
            # devices not under RLS.
            conflict_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql=(
                    "SELECT id FROM devices "
                    "WHERE location_tag = :tag "
                    "AND status = 'Pending-Pairing' "
                    "AND pairing_code IS NOT NULL "
                    "AND pairing_code_expires_at > NOW() "
                    "LIMIT 1"
                ),
                parameters=[{"name": "tag", "value": {"stringValue": location_tag}}],
            )
            if conflict_result["records"]:
                rds.commit_transaction(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    transactionId=tx["transactionId"],
                )
                return {
                    "statusCode": 409,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({
                        "error": "An unexpired pairing code already exists for this location_tag"
                    }),
                }

            insert_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql=(
                    "INSERT INTO devices "
                    "(location_tag, range_id, status, pairing_code, pairing_code_expires_at) "
                    "VALUES (:tag, :rid, 'Pending-Pairing', :code, :expires_at::TIMESTAMPTZ) "
                    "RETURNING id"
                ),
                parameters=[
                    {"name": "tag", "value": {"stringValue": location_tag}},
                    {"name": "rid", "value": {"stringValue": range_id}},
                    {"name": "code", "value": {"stringValue": _hash_pairing_code(pairing_code)}},
                    {"name": "expires_at", "value": {"stringValue": expires_at_str}},
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

        device_id = insert_result["records"][0][0]["stringValue"]

        body_out = {
            "device_id": device_id,
            "pairing_code": pairing_code,
            "expires_at": expires_at_str,
        }

        logger.info(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": device_id,
            "action": "admin_devices_pairing_code",
            "duration_ms": round((time.monotonic() - start) * 1000),
            "error": None,
        }))

        return {
            "statusCode": 201,
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
                "action": "admin_devices_pairing_code",
                "duration_ms": round((time.monotonic() - start) * 1000),
                "error": error_name,
            }))
