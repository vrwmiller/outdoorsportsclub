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
import time
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
_DEVICE_TOKEN_SALT: str | None = None
_device_salt_loaded_at: float = 0.0
_DEVICE_TOKEN_SALT_TTL_SECONDS: int = 60


def _load_device_token_salt(*, force: bool = False) -> str:
    """Return the HMAC salt, refreshing from Secrets Manager every 60 seconds.

    Using a short TTL means both handlers converge on a new salt within
    60 seconds of rotation, keeping pairing-code hashing consistent.
    """
    global _DEVICE_TOKEN_SALT, _device_salt_loaded_at
    now = time.time()
    if (
        not force
        and _DEVICE_TOKEN_SALT is not None
        and (now - _device_salt_loaded_at) < _DEVICE_TOKEN_SALT_TTL_SECONDS
    ):
        return _DEVICE_TOKEN_SALT
    raw = _sm.get_secret_value(SecretId=os.environ["DEVICE_TOKEN_SALT_ARN"])["SecretString"]
    try:
        salt = json.loads(raw)["salt"]
    except (json.JSONDecodeError, KeyError) as exc:
        raise RuntimeError(
            "DEVICE_TOKEN_SALT secret must be JSON with a 'salt' field"
        ) from exc
    _DEVICE_TOKEN_SALT = salt
    _device_salt_loaded_at = now
    return salt


# Fail fast at cold start if the secret is missing or malformed.
_load_device_token_salt(force=True)

CORS_HEADERS: dict[str, str] = {
    "Access-Control-Allow-Origin": CORS_ALLOW_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type,Authorization,x-device-token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PATCH,DELETE",
}


def _hash_pairing_code(code: str) -> str:
    """Return HMAC-SHA256 hex digest of the pairing code.

    Pairing codes are stored as this hash rather than plaintext so that a DB
    read-only breach cannot be used to register rogue kiosk devices.
    """
    salt = _load_device_token_salt()
    return hmac.new(salt.encode(), code.encode(), hashlib.sha256).hexdigest()


def _error(status: int, message: str) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": CORS_HEADERS,
        "body": json.dumps({"error": message}),
    }


def handler(event: dict, context: Any) -> dict[str, Any]:
    start = time.monotonic()
    device_id: str | None = None

    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 204, "headers": CORS_HEADERS, "body": ""}

    try:
        try:
            body = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON body") from exc

        pairing_code: str | None = body.get("pairing_code")
        if not pairing_code or not isinstance(pairing_code, str):
            raise ValueError("pairing_code is required")
        if len(pairing_code) < 6:
            raise ValueError("pairing_code is too short")
        if len(pairing_code) > 64:
            raise ValueError("pairing_code exceeds maximum length")

        rds = boto3.client("rds-data")

        # Generate the token before touching the DB to avoid a SELECT+UPDATE
        # race. The single UPDATE below validates code, status, and expiry
        # atomically — no separate SELECT is needed.
        raw_token: str = secrets.token_hex(32)
        salt = _load_device_token_salt()
        hashed_token: str = hmac.new(
            salt.encode(), raw_token.encode(), hashlib.sha256
        ).hexdigest()

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
                 WHERE pairing_code            = :code
                   AND status                  = 'Pending-Pairing'
                   AND pairing_code_expires_at > NOW()
                RETURNING id
            """,
            parameters=[
                {"name": "token_hash", "value": {"stringValue": hashed_token}},
                {"name": "code",       "value": {"stringValue": _hash_pairing_code(pairing_code)}},
            ],
        )

        if update.get("numberOfRecordsUpdated", 0) != 1:
            # Do not reveal whether the code was never issued, already used, or expired.
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.warning(json.dumps({
                "request_id": context.aws_request_id,
                "member_id": None,
                "device_id": None,
                "action": "pair_device",
                "duration_ms": duration_ms,
                "error": "InvalidPairingCode",
            }))
            return _error(400, "Invalid or expired pairing code")

        device_id = update["records"][0][0]["stringValue"]
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": None,
            "device_id": device_id,
            "action": "pair_device",
            "duration_ms": duration_ms,
            "error": None,
        }))
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"device_token": raw_token}),
        }

    except ValueError as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": None,
            "device_id": device_id,
            "action": "pair_device",
            "duration_ms": duration_ms,
            "error": type(exc).__name__,
        }))
        return _error(400, str(exc))
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.exception(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": None,
            "device_id": device_id,
            "action": "pair_device",
            "duration_ms": duration_ms,
            "error": type(exc).__name__,
        }))
        return _error(500, "Internal server error")
