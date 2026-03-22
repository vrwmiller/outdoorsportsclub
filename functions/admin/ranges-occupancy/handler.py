"""GET /v1/admin/ranges/occupancy  — Level 4+ RSO

Returns current lane occupancy for all ranges. Used by the Admin Portal for
the supervisory cross-range view, polled at a suitable interval.

Returns:
    200 OK  [ { range_id, name, is_open, lanes: [{ lane_id, lane_number,
                status, current_member_id, guest_count }] } ]
    403 Forbidden
    500 Internal Server Error
"""
import json
import logging
import time
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

        rds = boto3.client("rds-data")
        tx = rds.begin_transaction(
            resourceArn=DB_CLUSTER_ARN, secretArn=DB_SECRET_ARN, database=DB_NAME
        )
        try:
            # Admin policy: level 4+ can read all rows on RLS-protected tables.
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

            # ranges not under RLS; lanes not under RLS.
            ranges_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql="SELECT id, name, is_open FROM ranges ORDER BY name",
            )
            lanes_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql=(
                    "SELECT id, range_id, lane_number, status, current_member_id, guest_count "
                    "FROM lanes ORDER BY range_id, lane_number"
                ),
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

        # Group lanes by range_id.
        lanes_by_range: dict[str, list] = {}
        for row in lanes_result["records"]:
            rid = row[1]["stringValue"]
            lanes_by_range.setdefault(rid, []).append({
                "lane_id": row[0]["stringValue"],
                "lane_number": int(row[2]["longValue"]),
                "status": row[3]["stringValue"],
                "current_member_id": row[4].get("stringValue") if not row[4].get("isNull") else None,
                "guest_count": int(row[5]["longValue"]),
            })

        ranges_list = []
        for row in ranges_result["records"]:
            rid = row[0]["stringValue"]
            ranges_list.append({
                "range_id": rid,
                "name": row[1]["stringValue"],
                "is_open": row[2]["booleanValue"],
                "lanes": lanes_by_range.get(rid, []),
            })

        logger.info(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": None,
            "action": "admin_ranges_occupancy",
            "duration_ms": round((time.monotonic() - start) * 1000),
            "error": None,
        }))

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(ranges_list),
        }

    except PermissionError as exc:
        error_name = type(exc).__name__
        logger.warning("Auth failure [%s]: %s", context.aws_request_id, exc)
        return error_response(403, "Forbidden")
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
                "action": "admin_ranges_occupancy",
                "duration_ms": round((time.monotonic() - start) * 1000),
                "error": error_name,
            }))
