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


# ---------------------------------------------------------------------------
# Member / admin helpers
# ---------------------------------------------------------------------------

from tests.conftest import FAKE_MEMBER_ID  # noqa: E402 — avoid circular with top-level imports


def make_member_rds(sql_responses: dict, *, tx_id: str = "tx-1") -> MagicMock:
    """Return an rds-data mock for member/admin handler tests.

    ``sql_responses`` maps a SQL substring to the return value.
    The auth lookup (social_provider_id) is automatically injected
    so individual tests don't need to include it.

    The auth lookup returns a member row with id=FAKE_MEMBER_ID and
    training_level=3 by default.  Override with key
    ``"social_provider_id"`` to change auth behaviour.
    """
    auth_row = [
        {"stringValue": FAKE_MEMBER_ID},
        {"longValue": 3},
    ]
    full = {
        "WHERE social_provider_id =": {"records": [auth_row]},
        **sql_responses,
    }

    def _execute(**kwargs):
        sql = kwargs.get("sql", "")
        for key, val in full.items():
            if key in sql:
                return val
        return {"records": []}

    rds = MagicMock()
    rds.begin_transaction.return_value = {"transactionId": tx_id}
    rds.execute_statement.side_effect = _execute
    rds.commit_transaction.return_value = {}
    rds.rollback_transaction.return_value = {}
    return rds


def full_member_profile_row(
    member_num: str = "MBR-001",
    training_level: int = 3,
    service_hours: str = "0.00",
    dues_paid_until: str | None = "2030-12-31",
    waiver_signed_at: str | None = "2024-01-01T00:00:00Z",
    mobile_phone: str | None = "+15551234567",
    first_name: str | None = "Alice",
    last_name: str | None = "Smith",
    date_of_birth: str | None = "1990-01-01",
    street_address: str | None = "123 Main St",
    city: str | None = "Springfield",
    state: str | None = "IL",
    zip: str | None = "62701",
    notification_email: str | None = None,
    notify_email: bool = True,
    notify_sms: bool = False,
    notify_push: bool = False,
) -> list:
    """Build a members SELECT row matching the GET /v1/members/me projection."""
    return [
        {"stringValue": member_num},
        {"longValue": training_level},
        {"stringValue": service_hours},
        {"stringValue": dues_paid_until} if dues_paid_until else {"isNull": True},
        {"stringValue": waiver_signed_at} if waiver_signed_at else {"isNull": True},
        {"stringValue": mobile_phone} if mobile_phone else {"isNull": True},
        {"stringValue": first_name} if first_name is not None else {"isNull": True},
        {"stringValue": last_name} if last_name is not None else {"isNull": True},
        {"stringValue": date_of_birth} if date_of_birth is not None else {"isNull": True},
        {"stringValue": street_address} if street_address is not None else {"isNull": True},
        {"stringValue": city} if city is not None else {"isNull": True},
        {"stringValue": state} if state is not None else {"isNull": True},
        {"stringValue": zip} if zip is not None else {"isNull": True},
        {"stringValue": notification_email} if notification_email is not None else {"isNull": True},
        {"booleanValue": notify_email},
        {"booleanValue": notify_sms},
        {"booleanValue": notify_push},
    ]


def club_settings_row(annual_dues_cents: int = 10000) -> list:
    """Build a club_settings SELECT row."""
    return [
        {"longValue": annual_dues_cents},
        {"stringValue": "2024-01-01T00:00:00Z"},
        {"isNull": True},
    ]


def lane_row(
    lane_id: str = "lane-id-1",
    range_id: str = "range-id-1",
    lane_number: int = 1,
    status: str = "Available",
    current_member_id: str | None = None,
    guest_count: int = 0,
) -> list:
    """Build a lanes SELECT row."""
    return [
        {"stringValue": lane_id},
        {"stringValue": range_id},
        {"longValue": lane_number},
        {"stringValue": status},
        {"stringValue": current_member_id} if current_member_id else {"isNull": True},
        {"longValue": guest_count},
    ]


def range_row(
    range_id: str = "range-id-1",
    name: str = "Main Range",
    is_open: bool = True,
) -> list:
    """Build a ranges SELECT row."""
    return [
        {"stringValue": range_id},
        {"stringValue": name},
        {"booleanValue": is_open},
    ]
