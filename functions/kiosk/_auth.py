"""Shared device-token authentication for all kiosk Lambda handlers."""
import hashlib
import hmac
import json
import logging
import os
from typing import Any

import boto3

logger = logging.getLogger()

# ---------------------------------------------------------------------------
# Cold-start: resolve required env vars and cache Secrets Manager values
# ---------------------------------------------------------------------------

_REQUIRED_ENV = (
    "DB_CLUSTER_ARN",
    "DB_SECRET_ARN",
    "DB_NAME",
    "DEVICE_TOKEN_SALT_ARN",
    "CORS_ALLOW_ORIGIN",
)

for _var in _REQUIRED_ENV:
    if not os.environ.get(_var):
        raise RuntimeError(f"Missing required environment variable: {_var}")

DB_CLUSTER_ARN: str = os.environ["DB_CLUSTER_ARN"]
DB_SECRET_ARN: str = os.environ["DB_SECRET_ARN"]
DB_NAME: str = os.environ["DB_NAME"]
CORS_ALLOW_ORIGIN: str = os.environ["CORS_ALLOW_ORIGIN"]

_sm = boto3.client("secretsmanager")
_raw_salt_secret: str = _sm.get_secret_value(
    SecretId=os.environ["DEVICE_TOKEN_SALT_ARN"]
)["SecretString"]
try:
    # _DEVICE_TOKEN_SALT is fetched once at cold-start and cached for the
    # lifetime of the Lambda container.  After rotating this secret in
    # Secrets Manager, all kiosk Lambda containers must be force-cold-started
    # so they pick up the new salt — warm containers will continue using the
    # old value and will reject tokens generated against the new salt.
    # See docs/runbooks/secrets-rotation.md for the rotation procedure.
    _DEVICE_TOKEN_SALT: str = json.loads(_raw_salt_secret)["salt"]
except (json.JSONDecodeError, KeyError) as _exc:
    raise RuntimeError("DEVICE_TOKEN_SALT secret must be JSON with a 'salt' field") from _exc

CORS_HEADERS: dict[str, str] = {
    "Access-Control-Allow-Origin": CORS_ALLOW_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type,Authorization,x-device-token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PATCH,DELETE",
}

# SEC-15: Upper bound on member_num length enforced at the application layer.
# 64 characters exceeds any plausible badge identifier format; this prevents
# unbounded-length strings from reaching the DB query parameter.
# Centralised here so all kiosk handlers share the same limit.
MEMBER_NUM_MAX_LEN: int = 64


def error_response(status_code: int, message: str) -> dict[str, Any]:
    body = "Forbidden" if status_code == 403 else message
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps({"error": body}),
    }


def authenticate_device(event: dict) -> dict[str, Any]:
    """Validate x-device-token header and return the device row.

    Returns the device row dict with keys: id, range_id, status.
    Raises PermissionError if the token is missing, invalid, or the device is not Active.
    """
    headers: dict = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    raw_token: str | None = headers.get("x-device-token")
    if not raw_token:
        raise PermissionError("Missing x-device-token header")
    if len(raw_token) > 512:
        raise PermissionError("x-device-token header exceeds maximum length")

    hashed = hmac.new(
        _DEVICE_TOKEN_SALT.encode(), raw_token.encode(), hashlib.sha256
    ).hexdigest()

    rds = boto3.client("rds-data")
    result = rds.execute_statement(
        resourceArn=DB_CLUSTER_ARN,
        secretArn=DB_SECRET_ARN,
        database=DB_NAME,
        sql="SELECT id, range_id, status FROM devices WHERE device_token = :token",
        parameters=[{"name": "token", "value": {"stringValue": hashed}}],
    )

    rows = result.get("records", [])
    if not rows:
        raise PermissionError("Device not found")

    row = rows[0]
    device_id = row[0]["stringValue"]
    range_id = row[1]["stringValue"]
    status = row[2]["stringValue"]

    if status != "Active":
        raise PermissionError(f"Device status is not Active: {status}")

    return {"id": device_id, "range_id": range_id, "status": status}
