"""POST /v1/admin/lanes/{lane_id}/checkout  — Level 4+ RSO

Administrative force-checkout. Clears the specified occupied lane and writes
a Range-Checkout activity_log entry. After clearing, advances the wait list:
promotes the next Waiting entry to Called, records called_at, sets expires_at
(5 minutes), and sends an SNS SMS if the member has a mobile_phone.

Returns 409 Conflict if the lane is not Occupied.

Returns:
    200 OK
    403 Forbidden
    404 Not Found
    409 Conflict (lane not occupied)
    500 Internal Server Error
"""
import json
import logging
import os
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

_SNS_TOPIC_ARN = os.environ.get("SNS_ALERTS_TOPIC_ARN", "")


def handler(event: dict, context: Any) -> dict:
    start = time.monotonic()
    actor_member_id: str | None = None
    error_name: str | None = None

    try:
        member = authenticate_member(event)
        actor_member_id = member["member_id"]
        require_level(member, 4)

        path_params = event.get("pathParameters") or {}
        lane_id = path_params.get("lane_id")
        if not lane_id:
            raise ValueError("lane_id path parameter is required")

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
                parameters=[{"name": "mid", "value": {"stringValue": actor_member_id}}],
            )
            rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql="SELECT set_config('app.current_training_level', :level, true)",
                parameters=[{"name": "level", "value": {"stringValue": str(member["training_level"])}}],
            )

            # Fetch lane to validate it exists and is Occupied.
            lane_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql="SELECT id, range_id, status, current_member_id FROM lanes WHERE id = :lid",
                parameters=[{"name": "lid", "value": {"stringValue": lane_id}}],
            )
            if not lane_result["records"]:
                rds.commit_transaction(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    transactionId=tx["transactionId"],
                )
                return {
                    "statusCode": 404,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"error": "Lane not found"}),
                }

            lane_row = lane_result["records"][0]
            lane_status = lane_row[2]["stringValue"]
            if lane_status != "Occupied":
                rds.commit_transaction(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    transactionId=tx["transactionId"],
                )
                return {
                    "statusCode": 409,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"error": "Lane is not Occupied"}),
                }

            range_id = lane_row[1]["stringValue"]
            occupant_member_id = lane_row[3].get("stringValue") if not lane_row[3].get("isNull") else None

            # Clear the lane.
            rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql=(
                    "UPDATE lanes "
                    "SET status = 'Available', current_member_id = NULL, "
                    "    guest_count = 0, checked_in_at = NULL "
                    "WHERE id = :lid"
                ),
                parameters=[{"name": "lid", "value": {"stringValue": lane_id}}],
            )

            # Activity log — Range-Checkout with actor_member_id = RSO.
            if occupant_member_id:
                rds.execute_statement(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    database=DB_NAME,
                    transactionId=tx["transactionId"],
                    sql=(
                        "INSERT INTO activity_logs "
                        "(member_id, actor_member_id, activity_type, lane_id) "
                        "VALUES (:occupant, :actor, 'Range-Checkout', :lid)"
                    ),
                    parameters=[
                        {"name": "occupant", "value": {"stringValue": occupant_member_id}},
                        {"name": "actor", "value": {"stringValue": actor_member_id}},
                        {"name": "lid", "value": {"stringValue": lane_id}},
                    ],
                )

            # Advance wait list: promote next Waiting entry to Called.
            next_result = rds.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                transactionId=tx["transactionId"],
                sql=(
                    "UPDATE wait_list "
                    "SET status = 'Called', "
                    "    called_at = NOW(), "
                    "    expires_at = NOW() + INTERVAL '5 minutes' "
                    "WHERE id = ("
                    "  SELECT id FROM wait_list "
                    "  WHERE range_id = :rid AND status = 'Waiting' "
                    "  ORDER BY position LIMIT 1"
                    ") "
                    "RETURNING id"
                ),
                parameters=[{"name": "rid", "value": {"stringValue": range_id}}],
            )

            # Fetch mobile_phone for the Called member if a wait list entry was advanced.
            called_member_phone: str | None = None
            if next_result["records"]:
                called_wl_id = next_result["records"][0][0]["stringValue"]
                phone_result = rds.execute_statement(
                    resourceArn=DB_CLUSTER_ARN,
                    secretArn=DB_SECRET_ARN,
                    database=DB_NAME,
                    transactionId=tx["transactionId"],
                    sql=(
                        "SELECT m.mobile_phone FROM members m "
                        "JOIN wait_list wl ON wl.member_id = m.id "
                        "WHERE wl.id = :wl_id"
                    ),
                    parameters=[{"name": "wl_id", "value": {"stringValue": called_wl_id}}],
                )
                if phone_result["records"] and not phone_result["records"][0][0].get("isNull"):
                    called_member_phone = phone_result["records"][0][0].get("stringValue")

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

        # Send SNS SMS after the transaction commits.
        if called_member_phone and _SNS_TOPIC_ARN:
            try:
                sns = boto3.client("sns")
                sns.publish(
                    TopicArn=_SNS_TOPIC_ARN,
                    Message="A lane is now available at the range. Please check in at the kiosk.",
                    MessageAttributes={
                        "AWS.SNS.SMS.SMSType": {
                            "DataType": "String",
                            "StringValue": "Transactional",
                        }
                    },
                )
            except Exception as sns_exc:
                logger.error(
                    "SNS publish failed after admin checkout [%s]: %s",
                    context.aws_request_id,
                    sns_exc,
                )

        logger.info(json.dumps({
            "request_id": context.aws_request_id,
            "member_id": actor_member_id,
            "device_id": None,
            "action": "admin_lanes_checkout",
            "duration_ms": round((time.monotonic() - start) * 1000),
            "error": None,
        }))

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Lane cleared and wait list advanced"}),
        }

    except PermissionError as exc:
        error_name = type(exc).__name__
        logger.warning("Auth failure [%s]: %s", context.aws_request_id, exc)
        return error_response(403, "Forbidden")
    except (ValueError, json.JSONDecodeError) as exc:
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
                "member_id": actor_member_id,
                "device_id": None,
                "action": "admin_lanes_checkout",
                "duration_ms": round((time.monotonic() - start) * 1000),
                "error": error_name,
            }))
