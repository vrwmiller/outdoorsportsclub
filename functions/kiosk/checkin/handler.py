"""POST /v1/kiosk/check-in

Validates the scanning member's training level, dues, and guest count,
then either assigns an available lane or adds the member to the wait list.

Expected request body:
    { "member_num": "<qr_badge_value>", "guest_count": 0|1|2 }
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
    member_id: str | None = None
    error_name: str | None = None

    try:
        device = authenticate_device(event)
        range_id: str = device["range_id"]
        device_id: str = device["id"]

        body = json.loads(event.get("body") or "{}")
        member_num: str | None = body.get("member_num")
        if not member_num:
            raise ValueError("member_num is required")
        raw_guest_count = body.get("guest_count", 0)
        if not isinstance(raw_guest_count, int) or raw_guest_count < 0 or raw_guest_count > 2:
            raise ValueError("guest_count must be 0, 1, or 2")
        guest_count: int = raw_guest_count

        rds = boto3.client("rds-data")

        # One outer transaction for the entire handler; SERIALIZABLE must be first
        # (before any reads), then set_config before any RLS-protected reads.
        outer_tx = rds.begin_transaction(
            resourceArn=DB_CLUSTER_ARN, secretArn=DB_SECRET_ARN, database=DB_NAME
        )
        try:
            # SERIALIZABLE must precede all reads — prevents the MAX(position)+1 race
            # on the wait-list INSERT path when two concurrent check-ins race for the
            # same range.  Paired with idx_wait_list_range_position_active as a DB-level
            # belt-and-suspenders guard (migration 0022).
            rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=outer_tx["transactionId"],
                sql="SET TRANSACTION ISOLATION LEVEL SERIALIZABLE",
            )
            # Set RLS session variable — kiosk acts with training_level 4 (admin).
            rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=outer_tx["transactionId"],
                sql="SELECT set_config('app.current_training_level', '4', true)",
            )

            # 1. Resolve member from QR badge number
            m_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=outer_tx["transactionId"],
                sql=(
                    "SELECT id, training_level, dues_paid_until "
                    "FROM members WHERE member_num = :member_num"
                ),
                parameters=[{"name": "member_num", "value": {"stringValue": member_num}}],
            )
            if not m_result["records"]:
                raise PermissionError("Unknown member badge")
            m_row = m_result["records"][0]
            member_id = m_row[0]["stringValue"]
            training_level: int = int(m_row[1]["longValue"])
            dues_paid_until = m_row[2].get("stringValue")  # NULL if never paid

            # 2. Resolve range — check is_open and min_training_level
            r_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=outer_tx["transactionId"],
                sql="SELECT is_open, min_training_level FROM ranges WHERE id = :range_id",
                parameters=[{"name": "range_id", "value": {"stringValue": range_id}}],
            )
            if not r_result["records"]:
                raise ValueError("Range not found for this device")
            r_row = r_result["records"][0]
            is_open: bool = r_row[0]["booleanValue"]
            min_level: int = int(r_row[1]["longValue"])

            if not is_open:
                raise PermissionError("Range is closed")

            if training_level < min_level:
                raise PermissionError(f"Level {min_level} required to access this range")

            # 3. Dues current? dues_paid_until >= today (UTC)
            import datetime
            today = datetime.date.today().isoformat()
            if not dues_paid_until or dues_paid_until < today:
                raise PermissionError("Dues are not current")

            # 4. Policy: max_guests for this training_level
            p_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=outer_tx["transactionId"],
                sql="SELECT max_guests FROM training_level_policies WHERE training_level = :level",
                parameters=[{"name": "level", "value": {"longValue": training_level}}],
            )
            if not p_result["records"]:
                raise PermissionError("No policy found for this training level")
            max_guests: int = int(p_result["records"][0][0]["longValue"])
            if guest_count > max_guests:
                raise PermissionError(
                    f"Guest limit exceeded: level {training_level} allows {max_guests} guest(s)"
                )

            # 5+6. Single query for any active wait-list entry (Waiting OR Called).
            # Two separate reads were a race: a Called entry could be missed and cause
            # a duplicate-key violation on idx_wait_list_active_member_range.
            active_wl = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=outer_tx["transactionId"],
                sql=(
                    "SELECT id, status FROM wait_list "
                    "WHERE member_id = :member_id AND range_id = :range_id "
                    "AND status IN ('Waiting', 'Called')"
                ),
                parameters=[
                    {"name": "member_id", "value": {"stringValue": member_id}},
                    {"name": "range_id", "value": {"stringValue": range_id}},
                ],
            )
            called_entry_id: str | None = None
            if active_wl["records"]:
                entry_status = active_wl["records"][0][1]["stringValue"]
                if entry_status == "Waiting":
                    raise PermissionError("Member already has an active wait list entry for this range")
                # entry_status == 'Called': member is responding to their queue call — fall through
                # to lane assignment below; do NOT add another wait-list row.
                called_entry_id = active_wl["records"][0][0]["stringValue"]

            # 7. Find available lanes for this range
            lanes_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=outer_tx["transactionId"],
                sql=(
                    "SELECT id, lane_number FROM lanes "
                    "WHERE range_id = :range_id AND status = 'Available' "
                    "ORDER BY lane_number"
                ),
                parameters=[{"name": "range_id", "value": {"stringValue": range_id}}],
            )
            available_lanes = [
                {"id": row[0]["stringValue"], "lane_number": int(row[1]["longValue"])}
                for row in lanes_result["records"]
            ]

            if not available_lanes:
                # Range is full. Members with a Called entry cannot re-join the queue.
                if called_entry_id:
                    raise PermissionError(
                        "Your lane call has expired and the range is full. Please wait to be called again."
                    )
                # Position + insert must be atomic to prevent duplicates.
                pos_result = rds.execute_statement(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    database=DB_NAME,
                    transactionId=outer_tx["transactionId"],
                    sql=(
                        "SELECT COALESCE(MAX(position), 0) + 1 FROM wait_list "
                        "WHERE range_id = :range_id AND status = 'Waiting'"
                    ),
                    parameters=[{"name": "range_id", "value": {"stringValue": range_id}}],
                )
                wait_position: int = int(pos_result["records"][0][0]["longValue"])

                rds.execute_statement(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    database=DB_NAME,
                    transactionId=outer_tx["transactionId"],
                    sql=(
                        "INSERT INTO wait_list "
                        "(id, range_id, member_id, device_id, guest_count, position, status, joined_at) "
                        "VALUES (gen_random_uuid(), :range_id, :member_id, :device_id, "
                        ":guest_count, :position, 'Waiting', now())"
                    ),
                    parameters=[
                        {"name": "range_id", "value": {"stringValue": range_id}},
                        {"name": "member_id", "value": {"stringValue": member_id}},
                        {"name": "device_id", "value": {"stringValue": device_id}},
                        {"name": "guest_count", "value": {"longValue": guest_count}},
                        {"name": "position", "value": {"longValue": wait_position}},
                    ],
                )
                rds.commit_transaction(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    transactionId=outer_tx["transactionId"],
                )
                duration_ms = int((time.monotonic() - start) * 1000)
                logger.info(json.dumps({
                    "request_id": context.aws_request_id,
                    "member_id": member_id,
                    "device_id": device_id,
                    "action": "checkin",
                    "training_level": training_level,
                    "duration_ms": duration_ms,
                    "error": None,
                    "outcome": "wait_listed",
                    "wait_position": wait_position,
                }))
                return {
                    "statusCode": 202,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"wait_position": wait_position}),
                }

            # 8. Select lane that maximises spacing from occupied lanes
            occupied_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=outer_tx["transactionId"],
                sql=(
                    "SELECT lane_number FROM lanes "
                    "WHERE range_id = :range_id AND status = 'Occupied'"
                ),
                parameters=[{"name": "range_id", "value": {"stringValue": range_id}}],
            )
            occupied_numbers = {int(row[0]["longValue"]) for row in occupied_result["records"]}

            def min_distance(lane_num: int) -> int:
                if not occupied_numbers:
                    return 999  # no occupied lanes — all distances equal
                return min(abs(lane_num - occ) for occ in occupied_numbers)

            selected_lane = max(available_lanes, key=lambda lane: min_distance(lane["lane_number"]))
            lane_id: str = selected_lane["id"]
            lane_number: int = selected_lane["lane_number"]

            # 9. Assign lane — write activity_log inside the outer transaction
            lane_update = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=outer_tx["transactionId"],
                sql=(
                    "UPDATE lanes SET status = 'Occupied', "
                    "current_member_id = :member_id, guest_count = :guest_count, "
                    "checked_in_at = now() WHERE id = :lane_id AND status = 'Available'"
                ),
                parameters=[
                    {"name": "member_id", "value": {"stringValue": member_id}},
                    {"name": "guest_count", "value": {"longValue": guest_count}},
                    {"name": "lane_id", "value": {"stringValue": lane_id}},
                ],
            )
            if lane_update.get("numberOfRecordsUpdated", 0) == 0:
                rds.rollback_transaction(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    transactionId=outer_tx["transactionId"],
                )
                return {
                    "statusCode": 409,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"error": "Lane no longer available; please retry"}),
                }
            rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=outer_tx["transactionId"],
                sql=(
                    "INSERT INTO activity_logs "
                    "(member_id, device_id, lane_id, activity_type, timestamp) "
                    "VALUES (:member_id, :device_id, :lane_id, 'Range-Checkin', now())"
                ),
                parameters=[
                    {"name": "member_id", "value": {"stringValue": member_id}},
                    {"name": "device_id", "value": {"stringValue": device_id}},
                    {"name": "lane_id", "value": {"stringValue": lane_id}},
                ],
            )
            # If the member was called from the wait list, mark that entry Checked-In
            if called_entry_id:
                rds.execute_statement(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    database=DB_NAME,
                    transactionId=outer_tx["transactionId"],
                    sql=(
                        "UPDATE wait_list SET status = 'Checked-In' WHERE id = :entry_id"
                    ),
                    parameters=[
                        {"name": "entry_id", "value": {"stringValue": called_entry_id}}
                    ],
                )
            rds.commit_transaction(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                transactionId=outer_tx["transactionId"],
            )
        except Exception:
            rds.rollback_transaction(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                transactionId=outer_tx["transactionId"],
            )
            raise

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": device_id,
            "action": "checkin",
            "training_level": training_level,
            "duration_ms": duration_ms,
            "error": None,
            "outcome": "lane_assigned",
            "lane_number": lane_number,
        }))
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"lane_number": lane_number}),
        }

    except PermissionError as exc:
        error_name = type(exc).__name__
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": None,
            "action": "checkin",
            "training_level": None,
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
            "action": "checkin",
            "training_level": None,
            "duration_ms": duration_ms,
            "error": error_name,
        }))
        return error_response(400, str(exc))
    except Exception as exc:  # noqa: BLE001
        error_name = type(exc).__name__
        duration_ms = int((time.monotonic() - start) * 1000)
        _msg = str(exc)
        is_serialization_error = "40001" in _msg or "could not serialize" in _msg.lower()
        is_expected_unique_violation = "23505" in _msg and (
            "idx_wait_list_range_position_active" in _msg
            or "idx_wait_list_active_member_range" in _msg
        )
        if is_serialization_error or is_expected_unique_violation:
            logger.error(json.dumps({
                "request_id": context.aws_request_id,
                "member_id": member_id,
                "device_id": device_id,
                "action": "checkin",
                "training_level": None,
                "duration_ms": duration_ms,
                "error": "serialization_failure",
            }))
            return error_response(503, "Service temporarily unavailable, please retry")
        logger.exception(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": member_id,
            "device_id": None,
            "action": "checkin",
            "training_level": None,
            "duration_ms": duration_ms,
            "error": error_name,
        }))
        return error_response(500, "Internal server error")
