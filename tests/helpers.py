"""Shared SQL-keyword mock dispatch helper for kiosk handler tests.

Usage:
    rds = make_rds(sql_responses={
        "set_config": {},
        "FROM members": {"records": [member_row()]},
        ...
    })
    rds.begin_transaction.return_value = {"transactionId": "tx-1"}
"""
from unittest.mock import MagicMock

from tests.conftest import active_device_row


def member_row(
    member_id="member-id-1",
    training_level=3,
    dues_paid_until="2030-01-01",
):
    return [
        {"stringValue": member_id},
        {"longValue": training_level},
        {"stringValue": dues_paid_until},
    ]


def make_rds(sql_responses: dict, *, tx_id: str = "tx-1") -> MagicMock:
    """Return an rds-data mock that dispatches execute_statement by SQL keyword.

    The ``sql_responses`` dict maps a substring of the expected SQL to the
    return value for that call.  The device-token lookup is always injected
    so auth tests don't need to include it.
    """
    # Inject device auth response if not overridden
    full = {
        "WHERE device_token": {"records": [active_device_row()]},
        **sql_responses,
    }

    def _execute_statement(**kwargs):
        sql = kwargs.get("sql", "")
        for key, val in full.items():
            if key in sql:
                return val
        return {"records": []}

    rds = MagicMock()
    rds.begin_transaction.return_value = {"transactionId": tx_id}
    rds.execute_statement.side_effect = _execute_statement
    rds.commit_transaction.return_value = {}
    rds.rollback_transaction.return_value = {}
    return rds


def device_auth_only_rds(*, status: str = "Active") -> MagicMock:
    """Return an rds-data mock that responds to device-token lookup only."""
    row = [
        {"stringValue": "device-id-1"},
        {"stringValue": "range-id-1"},
        {"stringValue": status},
    ]
    rds = MagicMock()
    rds.execute_statement.return_value = {"records": [row] if status else []}
    return rds
