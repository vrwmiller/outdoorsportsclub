"""POST /v1/devices/pair

Validates a one-time pairing code and activates the device.
Returns the raw device token exactly once — it is never stored in plaintext.

Expected request body:
    { "pairing_code": "<alphanumeric-code>" }

Returns:
    200 OK  { "device_token": "<raw-hex-token>" }
    400 Bad Request  (invalid, expired, or already-used pairing code)
    500 Internal Server Error
"""
import hashlib
import hmac
import json
import logging
import os
import secrets
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Cold-start: resolve required env vars and cache the HMAC salt
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
_raw_salt: str = _sm.get_secret_value(
    SecretId=os.environ["DEVICE_TOKEN_SALT_ARN"]
)["SecretString"]
try:
    _DEVICE_TOKEN_SALT: str = json.loads(_raw_salt)["salt"]
except (json.JSONDecodeError, KeyError) as _exc:
    raise RuntimeError(
        "DEVICE_TOKEN_SALT secret must be JSON with a 'salt' field"
    ) from _exc

CORS_HEADERS: dict[str, str] = {
    "Access-Control-Allow-Origin": CORS_ALLOW_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "OPTIONS,POST",
}


def _error(status: int, message: str) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": CORS_HEADERS,
        "body": json.dumps({"error": message}),
    }


def lambda_handler(event: dict, context: Any) -> dict[str, Any]:
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 204, "headers": CORS_HEADERS, "body": ""}

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _error(400, "Invalid JSON body")

    pairing_code: str | None = body.get("pairing_code")
    if not pairing_code or not isinstance(pairing_code, str):
        return _error(400, "pairing_code is required")
    if len(pairing_code) > 64:
        return _error(400, "pairing_code exceeds maximum length")

    rds = boto3.client("rds-data")

    # Resolve device by pairing code. Filter on status and expiry in the
    # query so a single lookup confirms all validity conditions atomically.
    result = rds.execute_statement(
        resourceArn=DB_CLUSTER_ARN,
        secretArn=DB_SECRET_ARN,
        database=DB_NAME,
        sql="""
            SELECT id
            FROM devices
            WHERE pairing_code             = :code
              AND status                   = 'Pending-Pairing'
              AND pairing_code_expires_at  > NOW()
        """,
        parameters=[{"name": "code", "value": {"stringValue": pairing_code}}],
    )

    rows = result.get("records", [])
    if not rows:
        # Do not reveal whether the code exists but is expired vs never issued.
        logger.warning("Pairing attempt failed — code invalid or expired")
        return _error(400, "Invalid or expired pairing code")

    device_id: str = rows[0][0]["stringValue"]

    # Generate a 256-bit random token and store its HMAC hash.
    raw_token: str = secrets.token_hex(32)
    hashed_token: str = hmac.new(
        _DEVICE_TOKEN_SALT.encode(), raw_token.encode(), hashlib.sha256
    ).hexdigest()

    # Activate the device. The WHERE clause re-checks status to guard against
    # a concurrent pairing attempt on the same code.
    update = rds.execute_statement(
        resourceArn=DB_CLUSTER_ARN,
        secretArn=DB_SECRET_ARN,
        database=DB_NAME,
        sql="""
            UPDATE devices
               SET device_token            = :token_hash,
                   status                  = 'Active',
                   pairing_code            = NULL,
                   pairing_code_expires_at = NULL
             WHERE id     = :device_id
               AND status = 'Pending-Pairing'
        """,
        parameters=[
            {"name": "token_hash", "value": {"stringValue": hashed_token}},
            {"name": "device_id",  "value": {"stringValue": device_id}},
        ],
    )

    if update.get("numberOfRecordsUpdated", 0) != 1:
        # Another request activated this device between our SELECT and UPDATE.
        logger.error(
            "Concurrent pairing detected for device %s — UPDATE matched 0 rows",
            device_id,
        )
        return _error(400, "Invalid or expired pairing code")

    logger.info("Device %s successfully paired", device_id)

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({"device_token": raw_token}),
    }
