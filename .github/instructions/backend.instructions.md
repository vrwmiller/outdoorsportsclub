---
description: "Use when writing, editing, or reviewing Python AWS Lambda functions. Covers handler structure, RDS Data API patterns, Cognito JWT validation, Stripe integration, S3 waiver storage, SNS notifications, and error handling conventions for the Outdoor Sports Club project."
applyTo: "functions/**/*.py"
---

# Backend Standards — Outdoor Sports Club

## AWS Services in Use

| Service | Purpose |
| :--- | :--- |
| **AWS Lambda** (Python 3.12) | All backend logic — one function per endpoint |
| **AWS API Gateway** | REST API — routes map 1-to-1 to Lambda functions |
| **Amazon Aurora Serverless v2** | PostgreSQL database — accessed via **RDS Data API** only |
| **AWS Cognito** | Member JWT auth; Social Login (Google/Facebook) |
| **AWS Secrets Manager** | All runtime secrets (DB credentials, Stripe keys, device token salt) |
| **Amazon S3** + S3 Object Lock | Signed waiver storage — Compliance Mode, 7-year retention |
| **Amazon SNS** | SMS notifications for range closures and safety alerts |
| **AWS KMS** | Encryption at rest for S3, Aurora, and Secrets Manager |
| **Amazon CloudWatch** | Structured logging from all Lambda functions |

## Handler Structure

Every Lambda handler follows this pattern:

```python
import json
import logging
import os
from typing import Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: dict, context: Any) -> dict:
    try:
        # 1. Authenticate
        # 2. Validate input
        # 3. Execute business logic
        # 4. Return success response
        return {"statusCode": 200, "body": json.dumps({"message": "OK"})}
    except PermissionError as exc:
        logger.warning("Auth failure: %s", exc)
        return {"statusCode": 403, "body": json.dumps({"error": "Forbidden"})}
    except ValueError as exc:
        logger.warning("Validation error: %s", exc)
        return {"statusCode": 400, "body": json.dumps({"error": str(exc)})}
    except Exception as exc:  # noqa: BLE001 — final safety net; log and sanitise
        logger.exception("Unhandled error: %s", exc)
        return {"statusCode": 500, "body": json.dumps({"error": "Internal server error"})}
```

* Return dicts must always include `statusCode` (int) and `body` (JSON string)
* Never return raw exception messages or stack traces to the client
* Log exceptions with `logger.exception()` for CloudWatch; the client receives only a sanitised message

## Authentication

### Member endpoints (Cognito JWT)

* Extract the JWT from `event["headers"]["Authorization"]` (Bearer token)
* Validate the token against the Cognito JWKS endpoint — use `python-jose` or `PyJWT` with the Cognito public keys
* After validating the JWT, **always query the `members` table via the RDS Data API to get the authoritative `training_level`** — do not trust the `training_level` value from the token claim, as it may be stale if the level was updated since the token was issued. Use the Cognito `sub` claim to look up the member record.
* Enforce the minimum required level against the value fetched from the database before executing any logic
* Reject missing or invalid tokens with `403 Forbidden` — never `401` (Cognito handles the 401 flow)

### Kiosk endpoints (Device Token)

* Extract `x-device-token` from `event["headers"]`
* Query the `devices` table via the **RDS Data API**: `SELECT status FROM devices WHERE device_token = :token`
* Reject tokens where `status != 'Active'` with `403 Forbidden`
* Never log the raw device token value

## Database — RDS Data API

* Use `boto3` client `rds-data` — never bundle `psycopg2` or open a persistent connection inside a Lambda function
* All queries must use parameterised statements — never use string interpolation for user-supplied values (SQL injection prevention)
* Reference the cluster ARN and secret ARN from environment variables: `DB_CLUSTER_ARN`, `DB_SECRET_ARN`, `DB_NAME`
* Transaction pattern for multi-step writes (e.g., write `activity_logs` after Stripe payment confirms):

```python
import boto3

rds = boto3.client("rds-data")

tx = rds.begin_transaction(resourceArn=CLUSTER_ARN, secretArn=SECRET_ARN, database=DB_NAME)
try:
    rds.execute_statement(..., transactionId=tx["transactionId"])
    rds.commit_transaction(resourceArn=CLUSTER_ARN, secretArn=SECRET_ARN, transactionId=tx["transactionId"])
except Exception:
    rds.rollback_transaction(resourceArn=CLUSTER_ARN, secretArn=SECRET_ARN, transactionId=tx["transactionId"])
    raise
```

## Secrets & Environment Variables

* All secrets are fetched at cold-start from **AWS Secrets Manager** — cache in a module-level variable; never re-fetch per invocation
* Environment variable names:

| Variable | Contains |
| :--- | :--- |
| `DB_CLUSTER_ARN` | Aurora cluster ARN |
| `DB_SECRET_ARN` | Secrets Manager ARN for DB credentials |
| `DB_NAME` | Database name |
| `COGNITO_USER_POOL_ID` | Cognito User Pool ID |
| `COGNITO_REGION` | AWS region for Cognito JWKS lookup |
| `STRIPE_SECRET_ARN` | Secrets Manager ARN for Stripe secret key |
| `S3_WAIVER_BUCKET` | S3 bucket name for signed waivers |
| `SNS_ALERTS_TOPIC_ARN` | SNS topic ARN for range alerts |

## Stripe Integration

* Stripe secret key is fetched at cold-start from **AWS Secrets Manager** via `STRIPE_SECRET_ARN`
* Use `stripe.PaymentIntent` for all Tap to Pay flows — never store card data
* Confirm payment success via Stripe webhook or synchronous `PaymentIntent` status check before writing to the database
* On Stripe failure, return `402 Payment Required` with a sanitised error message

## S3 Waiver Storage

* Upload signed waivers to `S3_WAIVER_BUCKET` with a key pattern of `waivers/<member_id>/<timestamp>.pdf`
* Use server-side encryption: `ServerSideEncryption='aws:kms'`
* S3 Object Lock is configured at the bucket level (Compliance Mode, 7 years) — do not set object-level retention in code
* After successful upload, update `members.waiver_signed_at` via the RDS Data API in the same transaction

## API Gateway Integration

* All Lambda functions are integrated with API Gateway using **Lambda Proxy Integration** — the full HTTP request is forwarded as `event` and the return dict is used as the HTTP response verbatim
* CORS headers must be included in every response dict, including error responses; set the following at minimum:

```python
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "https://yourdomain.com",  # set via env var; never "*" in production
    "Access-Control-Allow-Headers": "Content-Type,Authorization,x-device-token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PATCH",
}
```

* Configure the `Access-Control-Allow-Origin` value from an environment variable (`CORS_ALLOW_ORIGIN`) — never hardcode the domain
* Member-facing routes use a **Cognito Authorizer** configured at the API Gateway level to reject requests with invalid or missing JWTs before they reach the Lambda function; the Lambda still validates `training_level` server-side
* Kiosk routes do **not** use the Cognito Authorizer — Device Token validation is handled entirely inside the Lambda handler

## SNS Notifications

* Publish to `SNS_ALERTS_TOPIC_ARN` for range-closure or safety events
* Message format: plain text, 160-character SMS limit; no PII in the message body
* Use `boto3` client `sns` with `MessageAttributes` to distinguish alert types if needed

## Coding Standards

* Follow PEP 8: 4-space indentation, max 100 characters per line
* All function parameters and return types must have type annotations
* Use f-strings for formatting — never `%` or `.format()`
* Use `os.environ` for environment variable access — raise a clear `RuntimeError` at cold-start if a required variable is missing
* One Lambda function per file; handler always named `handler(event, context)`
* No bare `except:` — always catch specific exception types; use a final broad `except Exception` only as a safety net with logging
* Keep handlers lean — no speculative abstractions, no dead code, no defensive handling of states the schema guarantees cannot occur. See the Code Complexity & Bloat rules in `.github/instructions/linter.instructions.md`.
