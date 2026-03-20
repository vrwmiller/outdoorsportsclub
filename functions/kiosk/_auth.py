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
_DEVICE_TOKEN_SALT: str = _sm.get_secret_value(
    SecretId=os.environ["DEVICE_TOKEN_SALT_ARN"]
)["SecretString"]

CORS_HEADERS: dict[str, str] = {
    "Access-Control-Allow-Origin": CORS_ALLOW_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type,Authorization,x-device-token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PATCH,DELETE",
}


def error_response(status_code: int, message: str) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps({"error": message}),
    }


def authenticate_device(event: dict) -> dict[str, Any]:
    """Validate x-device-token header and return the device row.

    Returns the device row dict with keys: id, range_id, status.
    Raises PermissionError if the token is missing, invalid, or the device is not Active.
    """
    headers: dict = event.get("headers") or {}
    raw_token: str | None = headers.get("x-device-token")
    if not raw_token:
        raise PermissionError("Missing x-device-token header")

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
