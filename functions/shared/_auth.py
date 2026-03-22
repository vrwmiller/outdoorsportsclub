"""Shared Cognito JWT authentication for member and admin Lambda handlers.

All member-facing and admin Lambda functions import this module. The JWT
is validated against the Cognito User Pool's public JWKS; the authoritative
training_level is always re-queried from Aurora — never read from the token.

Usage (in a handler):

    from _auth import authenticate_member, require_level, error_response, CORS_HEADERS
    from _auth import DB_CLUSTER_ARN, DB_SECRET_ARN, DB_NAME

    member = authenticate_member(event)       # raises PermissionError on failure
    require_level(member, 4)                  # raises PermissionError if level < 4
"""
import json
import logging
import os
import urllib.request
from typing import Any

import boto3
import jwt
from jwt.algorithms import RSAAlgorithm

logger = logging.getLogger()

# ---------------------------------------------------------------------------
# Cold-start: resolve required env vars
# ---------------------------------------------------------------------------

_REQUIRED_ENV = (
    "DB_CLUSTER_ARN",
    "DB_SECRET_ARN",
    "DB_NAME",
    "COGNITO_USER_POOL_ID",
    "COGNITO_REGION",
    "CORS_ALLOW_ORIGIN",
)

for _var in _REQUIRED_ENV:
    if not os.environ.get(_var):
        raise RuntimeError(f"Missing required environment variable: {_var}")

DB_CLUSTER_ARN: str = os.environ["DB_CLUSTER_ARN"]
DB_SECRET_ARN: str = os.environ["DB_SECRET_ARN"]
DB_NAME: str = os.environ["DB_NAME"]
_POOL_ID: str = os.environ["COGNITO_USER_POOL_ID"]
_REGION: str = os.environ["COGNITO_REGION"]
CORS_ALLOW_ORIGIN: str = os.environ["CORS_ALLOW_ORIGIN"]

CORS_HEADERS: dict[str, str] = {
    "Access-Control-Allow-Origin": CORS_ALLOW_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PATCH,DELETE",
}

# ---------------------------------------------------------------------------
# JWKS cache (fetched once per cold start)
# ---------------------------------------------------------------------------

_jwks_cache: dict | None = None


def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is None:
        url = (
            f"https://cognito-idp.{_REGION}.amazonaws.com"
            f"/{_POOL_ID}/.well-known/jwks.json"
        )
        with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
            _jwks_cache = json.loads(resp.read())
    return _jwks_cache


# ---------------------------------------------------------------------------
# JWT validation — testable as a standalone function (tests patch this)
# ---------------------------------------------------------------------------


def validate_cognito_jwt(token: str) -> dict:
    """Validate a Cognito JWT and return decoded claims.

    Raises PermissionError on any validation failure.
    """
    try:
        header = jwt.get_unverified_header(token)
    except jwt.exceptions.DecodeError as exc:
        raise PermissionError("Malformed JWT") from exc

    kid = header.get("kid")
    if not kid:
        raise PermissionError("JWT missing kid header")

    jwks = _get_jwks()
    key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if key_data is None:
        raise PermissionError("JWT key ID not found in JWKS")

    public_key = RSAAlgorithm.from_jwk(json.dumps(key_data))

    try:
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError as exc:
        raise PermissionError("JWT has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise PermissionError(f"Invalid JWT: {exc}") from exc

    return claims


# ---------------------------------------------------------------------------
# Member authentication — validates JWT + re-queries training_level from DB
# ---------------------------------------------------------------------------


def authenticate_member(event: dict) -> dict[str, Any]:
    """Authenticate a member request.

    Extracts the Bearer token, validates it against Cognito JWKS, then
    re-queries training_level from Aurora. Returns
    { "member_id": str, "sub": str, "training_level": int }.

    Raises PermissionError if auth fails at any step.
    """
    headers: dict = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    auth_header: str | None = headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise PermissionError("Missing or invalid Authorization header")

    token = auth_header[len("Bearer "):]
    if len(token) > 4096:
        raise PermissionError("Authorization token exceeds maximum length")

    claims = validate_cognito_jwt(token)
    sub: str | None = claims.get("sub")
    if not sub:
        raise PermissionError("JWT missing sub claim")

    # Re-query training_level from Aurora — never trust the JWT claim.
    rds = boto3.client("rds-data")
    tx = rds.begin_transaction(
        resourceArn=DB_CLUSTER_ARN, secretArn=DB_SECRET_ARN, database=DB_NAME
    )
    try:
        # Use admin-level GUC bypass (level 4) to look up the member by the
        # Cognito sub stored in social_provider_id — we don't know the members.id
        # UUID yet, so we cannot use the self-access policy here.
        rds.execute_statement(
            resourceArn=DB_CLUSTER_ARN,
            secretArn=DB_SECRET_ARN,
            database=DB_NAME,
            transactionId=tx["transactionId"],
            sql="SELECT set_config('app.current_training_level', '4', true)",
        )
        rds.execute_statement(
            resourceArn=DB_CLUSTER_ARN,
            secretArn=DB_SECRET_ARN,
            database=DB_NAME,
            transactionId=tx["transactionId"],
            sql="SELECT set_config('app.current_member_id', '00000000-0000-0000-0000-000000000000', true)",
        )

        result = rds.execute_statement(
            resourceArn=DB_CLUSTER_ARN,
            secretArn=DB_SECRET_ARN,
            database=DB_NAME,
            transactionId=tx["transactionId"],
            sql="SELECT id, training_level FROM members WHERE social_provider_id = :sub",
            parameters=[{"name": "sub", "value": {"stringValue": sub}}],
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
    member_id: str = row[0]["stringValue"]
    training_level: int = int(row[1]["longValue"])

    return {"member_id": member_id, "sub": sub, "training_level": training_level}


def require_level(member: dict, min_level: int) -> None:
    """Raise PermissionError if member's training_level is below min_level."""
    if member["training_level"] < min_level:
        raise PermissionError(
            f"Requires training level {min_level}; member has {member['training_level']}"
        )


def error_response(status_code: int, message: str) -> dict[str, Any]:
    body = "Forbidden" if status_code == 403 else message
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps({"error": body}),
    }
