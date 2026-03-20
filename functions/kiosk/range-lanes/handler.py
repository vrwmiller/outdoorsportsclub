"""GET /v1/kiosk/range/lanes

Returns current lane occupancy for the kiosk's own range.
Used by the RSO Dashboard for initial load, post-transaction re-fetch,
and the 30-second background poll.
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
    authenticate_device,
    error_response,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: dict, context: Any) -> dict:
    start = time.monotonic()
    error_name: str | None = None

    try:
        device = authenticate_device(event)
        range_id: str = device["range_id"]
        device_id: str = device["id"]

        rds = boto3.client("rds-data")

        # Range metadata
        r_result = rds.execute_statement(
            resourceArn=DB_CLUSTER_ARN,
            secretArn=DB_SECRET_ARN,
            database=DB_NAME,
            sql="SELECT name, is_open FROM ranges WHERE id = :range_id",
            parameters=[{"name": "range_id", "value": {"stringValue": range_id}}],
        )
        if not r_result["records"]:
            raise ValueError("Range not found for this device")
        r_row = r_result["records"][0]
        range_name: str = r_row[0]["stringValue"]
        is_open: bool = r_row[1]["booleanValue"]

        # Lane occupancy with member_num for display
        lanes_result = rds.execute_statement(
            resourceArn=DB_CLUSTER_ARN,
            secretArn=DB_SECRET_ARN,
            database=DB_NAME,
            sql=(
                "SELECT l.id, l.lane_number, l.status, l.current_member_id, "
                "m.member_num, l.guest_count, l.checked_in_at "
                "FROM lanes l "
                "LEFT JOIN members m ON m.id = l.current_member_id "
                "WHERE l.range_id = :range_id "
                "ORDER BY l.lane_number"
            ),
            parameters=[{"name": "range_id", "value": {"stringValue": range_id}}],
        )

        lanes = []
        for row in lanes_result["records"]:
            lane_id = row[0]["stringValue"]
            lane_number = int(row[1]["longValue"])
            status = row[2]["stringValue"]
            current_member_id = row[3].get("stringValue")
            member_num = row[4].get("stringValue")
            guest_count = int(row[5]["longValue"])
            checked_in_at = row[6].get("stringValue")
            lanes.append({
                "lane_id": lane_id,
                "lane_number": lane_number,
                "status": status,
                "current_member_id": current_member_id,
                "member_num": member_num,
                "guest_count": guest_count,
                "checked_in_at": checked_in_at,
            })

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": None,
            "device_id": device_id,
            "action": "range_lanes",
            "duration_ms": duration_ms,
            "error": None,
        }))
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({
                "range_id": range_id,
                "name": range_name,
                "is_open": is_open,
                "lanes": lanes,
            }),
        }

    except PermissionError as exc:
        error_name = type(exc).__name__
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": None,
            "device_id": None,
            "action": "range_lanes",
            "duration_ms": duration_ms,
            "error": error_name,
        }))
        return error_response(403, str(exc))
    except ValueError as exc:
        error_name = type(exc).__name__
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": None,
            "device_id": None,
            "action": "range_lanes",
            "duration_ms": duration_ms,
            "error": error_name,
        }))
        return error_response(400, str(exc))
    except Exception as exc:  # noqa: BLE001
        error_name = type(exc).__name__
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.exception(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": None,
            "device_id": None,
            "action": "range_lanes",
            "duration_ms": duration_ms,
            "error": error_name,
        }))
        return error_response(500, "Internal server error")
