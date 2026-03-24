"""POST /v1/kiosk/waiver

Stores a signed waiver PDF in S3 and records the event in Aurora.
Handles both member waivers and guest waivers based on presence of guest_id.

Expected request body:
    {
        "member_num": "<qr_badge_value>",
        "pdf_bytes": "<base64-encoded PDF>",
        "guest_id": "<uuid>"     # optional — omit for member waiver
    }

member_num is resolved server-side to members.id — the client never supplies
a UUID directly.
"""
import base64
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import boto3

from _auth import (
    DB_CLUSTER_ARN,
    DB_SECRET_ARN,
    DB_NAME,
    CORS_HEADERS,
    authenticate_device,
    error_response,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

if not os.environ.get("S3_WAIVER_BUCKET"):
    raise RuntimeError("Missing required environment variable: S3_WAIVER_BUCKET")

S3_WAIVER_BUCKET: str = os.environ["S3_WAIVER_BUCKET"]


def handler(event: dict, context: Any) -> dict:
    start = time.monotonic()
    member_id: str | None = None
    s3_key: str | None = None
    error_name: str | None = None

    try:
        device = authenticate_device(event)
        device_id: str = device["id"]

        body = json.loads(event.get("body") or "{}")
        member_num: str | None = body.get("member_num")
        if not member_num:
            raise ValueError("member_num is required")
        pdf_b64: str | None = body.get("pdf_bytes")
        if not pdf_b64:
            raise ValueError("pdf_bytes is required")
        guest_id: str | None = body.get("guest_id")

        # Validate guest_id is a UUID to prevent S3 key path traversal.
        # member_num is resolved server-side and never used directly in S3 keys.
        import re as _re
        _UUID_RE = _re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', _re.I
        )
        if guest_id and not _UUID_RE.match(guest_id):
            raise ValueError("guest_id must be a valid UUID")

        # Decode PDF — reject oversized or non-base64 payloads early
        _MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB
        if len(pdf_b64) > (_MAX_PDF_BYTES * 4 // 3 + 4):
            raise ValueError("pdf_bytes exceeds maximum allowed size (10 MB)")
        try:
            pdf_data = base64.b64decode(pdf_b64, validate=True)
        except Exception:
            raise ValueError("pdf_bytes must be valid base64")
        if len(pdf_data) > _MAX_PDF_BYTES:
            raise ValueError("Decoded PDF exceeds maximum allowed size (10 MB)")

        timestamp_str = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        s3 = boto3.client("s3")
        rds = boto3.client("rds-data")

        tx = rds.begin_transaction(
            resourceArn=DB_CLUSTER_ARN, secretArn=DB_SECRET_ARN, database=DB_NAME
        )
        try:
            # Set RLS session variable — kiosk acts with training_level 4 (admin).
            rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql="SELECT set_config('app.current_training_level', '4', true)",
            )

            # Resolve member badge number to internal member ID server-side.
            # Consistent with every other kiosk handler — the client never
            # supplies a UUID directly.
            m_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql="SELECT id FROM members WHERE member_num = :member_num",
                parameters=[
                    {"name": "member_num", "value": {"stringValue": member_num}}
                ],
            )
            if not m_result["records"]:
                raise PermissionError("Unknown member badge")
            member_id = m_result["records"][0][0]["stringValue"]

            # Set current_member_id GUC for activity_logs RLS kiosk-insert policy.
            rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql="SELECT set_config('app.current_member_id', :mid, true)",
                parameters=[
                    {"name": "mid", "value": {"stringValue": member_id}}
                ],
            )

            if guest_id:
                # ---- Guest waiver path ----
                s3_key = f"waivers/guests/{guest_id}/{timestamp_str}.pdf"
                # Pre-validate guest exists before uploading to avoid orphaned
                # S3 Object Lock objects.
                pre_check = rds.execute_statement(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    database=DB_NAME,
                    transactionId=tx["transactionId"],
                    sql="SELECT id FROM guests WHERE id = :guest_id",
                    parameters=[
                        {"name": "guest_id", "value": {"stringValue": guest_id}}
                    ],
                )
                if not pre_check["records"]:
                    raise ValueError("guest_id not found")
                s3.put_object(
                    Bucket=S3_WAIVER_BUCKET,
                    Key=s3_key,
                    Body=pdf_data,
                    ContentType="application/pdf",
                    ServerSideEncryption="aws:kms",
                )
                rds.execute_statement(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    database=DB_NAME,
                    transactionId=tx["transactionId"],
                    sql=(
                        "UPDATE guests SET waiver_signed_at = now(), "
                        "waiver_s3_key = :s3_key WHERE id = :guest_id"
                    ),
                    parameters=[
                        {"name": "s3_key", "value": {"stringValue": s3_key}},
                        {"name": "guest_id", "value": {"stringValue": guest_id}},
                    ],
                )
                rds.execute_statement(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    database=DB_NAME,
                    transactionId=tx["transactionId"],
                    sql=(
                        "INSERT INTO activity_logs "
                        "(member_id, device_id, guest_id, activity_type, "
                        "waiver_s3_key, timestamp) "
                        "VALUES (:member_id, :device_id, :guest_id, "
                        "'Waiver-Signed', :s3_key, now())"
                    ),
                    parameters=[
                        {"name": "member_id", "value": {"stringValue": member_id}},
                        {"name": "device_id", "value": {"stringValue": device_id}},
                        {"name": "guest_id", "value": {"stringValue": guest_id}},
                        {"name": "s3_key", "value": {"stringValue": s3_key}},
                    ],
                )

            else:
                # ---- Member waiver path ----
                s3_key = f"waivers/{member_id}/{timestamp_str}.pdf"
                s3.put_object(
                    Bucket=S3_WAIVER_BUCKET,
                    Key=s3_key,
                    Body=pdf_data,
                    ContentType="application/pdf",
                    ServerSideEncryption="aws:kms",
                )
                rds.execute_statement(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    database=DB_NAME,
                    transactionId=tx["transactionId"],
                    sql=(
                        "UPDATE members "
                        "SET waiver_signed_at = now(), "
                        "waiver_version = waiver_version + 1 "
                        "WHERE id = :member_id"
                    ),
                    parameters=[
                        {"name": "member_id", "value": {"stringValue": member_id}}
                    ],
                )
                rds.execute_statement(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    database=DB_NAME,
                    transactionId=tx["transactionId"],
                    sql=(
                        "INSERT INTO activity_logs "
                        "(member_id, device_id, activity_type, waiver_s3_key, timestamp) "
                        "VALUES (:member_id, :device_id, 'Waiver-Signed', :s3_key, now())"
                    ),
                    parameters=[
                        {"name": "member_id", "value": {"stringValue": member_id}},
                        {"name": "device_id", "value": {"stringValue": device_id}},
                        {"name": "s3_key", "value": {"stringValue": s3_key}},
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

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": device_id,
            "action": "waiver",
            "duration_ms": duration_ms,
            "error": None,
        }))
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Waiver stored"}),
        }

    except PermissionError as exc:
        error_name = type(exc).__name__
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": None,
            "action": "waiver",
            "s3_key": s3_key,
            "duration_ms": duration_ms,
            "error": error_name,
        }))
        return error_response(403, str(exc))
    except ValueError as exc:
        error_name = type(exc).__name__
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": None,
            "action": "waiver",
            "s3_key": s3_key,
            "duration_ms": duration_ms,
            "error": error_name,
        }))
        return error_response(400, str(exc))
    except Exception as exc:  # noqa: BLE001
        error_name = type(exc).__name__
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.exception(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": None,
            "action": "waiver",
            "s3_key": s3_key,
            "duration_ms": duration_ms,
            "error": error_name,
        }))
        return error_response(500, "Internal server error")
