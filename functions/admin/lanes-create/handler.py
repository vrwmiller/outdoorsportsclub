"""POST /v1/admin/lanes  — Level 4+ RSO

Creates a new lane for a range.

Body: { range_id, lane_number }

Returns:
    201 Created  { lane_id, range_id, lane_number, status }
    400 Bad Request (missing fields)
    403 Forbidden
    409 Conflict (duplicate lane number for this range)
    500 Internal Server Error
"""
import json
import logging
import time
import uuid
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


def handler(event: dict, context: Any) -> dict:
    start = time.monotonic()
    member_id: str | None = None
    error_name: str | None = None

    try:
        member = authenticate_member(event)
        member_id = member["member_id"]
        require_level(member, 4)

        body = json.loads(event.get("body") or "{}")
        range_id = body.get("range_id")
        lane_number = body.get("lane_number")

        if not isinstance(range_id, str) or not range_id:
            raise ValueError("range_id must be a non-empty string")
        try:
            range_id = str(uuid.UUID(range_id))
        except (ValueError, TypeError):
            raise ValueError("range_id must be a valid UUID")
        if lane_number is None:
            raise ValueError("lane_number is required")
        if (
            isinstance(lane_number, bool)
            or not isinstance(lane_number, int)
            or lane_number < 1
            or lane_number > 32767
        ):
            raise ValueError("lane_number must be a positive integer no greater than 32767")

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

            try:
                # lanes not under RLS; unique constraint (range_id, lane_number) enforces no dupes.
                result = rds.execute_statement(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    database=DB_NAME,
                    transactionId=tx["transactionId"],
                    sql=(
                        "INSERT INTO lanes (range_id, lane_number) "
                        "VALUES (:rid, :num) "
                        "RETURNING id, range_id, lane_number, status"
                    ),
                    parameters=[
                        {"name": "rid", "value": {"stringValue": range_id}},
                        {"name": "num", "value": {"longValue": lane_number}},
                    ],
                )
            except Exception as exc:
                if "uq_lanes_range_lane" in str(exc) or "unique" in str(exc).lower():
                    rds.rollback_transaction(
                        resourceArn=DB_CLUSTER_ARN,
                        secretArn=DB_SECRET_ARN,
                        transactionId=tx["transactionId"],
                    )
                    error_name = "ConflictError"
                    return {
                        "statusCode": 409,
                        "headers": CORS_HEADERS,
                        "body": json.dumps({"error": "Lane number already exists for this range"}),
                    }
                if "foreign key constraint" in str(exc).lower():
                    rds.rollback_transaction(
                        resourceArn=DB_CLUSTER_ARN,
                        secretArn=DB_SECRET_ARN,
                        transactionId=tx["transactionId"],
                    )
                    error_name = "ValidationError"
                    return {
                        "statusCode": 400,
                        "headers": CORS_HEADERS,
                        "body": json.dumps({"error": "range_id does not reference a valid range"}),
                    }
                raise

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

        row = result["records"][0]
        body_out = {
            "lane_id": row[0]["stringValue"],
            "range_id": row[1]["stringValue"],
            "lane_number": int(row[2]["longValue"]),
            "status": row[3]["stringValue"],
        }

        logger.info(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": None,
            "action": "admin_lanes_create",
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
    except json.JSONDecodeError:
        error_name = "JSONDecodeError"
        logger.warning("Validation error [%s]: invalid JSON body", context.aws_request_id)
        return error_response(400, "Invalid JSON body")
    except ValueError as exc:
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
                "action": "admin_lanes_create",
                "duration_ms": round((time.monotonic() - start) * 1000),
                "error": error_name,
            }))
