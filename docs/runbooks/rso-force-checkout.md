# RSO Force-Checkout

**Audience:** RSO / Instructor (Level 4) or above.

This runbook covers the administrative force-checkout procedure for clearing an occupied lane when a member is unable or unwilling to scan out normally — for example, during a weather closure, a range incident, or an emergency evacuation.

Force-checkout is the only supported mechanism for clearing an occupied lane without a member QR scan. See `docs/design.md` Section 4 (RSO Dashboard state) and `POST /v1/admin/lanes/{lane_id}/checkout`.

---

## When to use force-checkout

| Scenario | Notes |
| :--- | :--- |
| Weather closure or outdoor range shutdown | Shooter has left the range; kiosk scan is not practical |
| Range incident requiring immediate range clear | All occupied lanes must be cleared to complete the incident closure |
| Member leaves without scanning out | Shooter departed without checking out at the kiosk |
| Emergency evacuation | Clear all lanes after confirming the range is physically empty |

> Force-checkout is **not** an override for check-in violations. Use the **Violation alert** RSO override flow on the kiosk for those cases — force-checkout only applies to lanes that are already occupied.

---

## Prerequisites

* A Level 4+ badge (NFC or QR) to authenticate on the kiosk, **or** a Level 4+ session in the **Admin Portal**
* Physical confirmation that the lane's occupant has actually vacated (force-checkout clears the lane immediately — confirm before proceeding)

---

## Procedure A — Force-checkout from the kiosk RSO Dashboard

1. At the kiosk, scan your Level 4+ QR badge from the **Idle** screen
2. At the **role prompt**, select **Open RSO Dashboard**
3. The RSO Dashboard shows all lanes for this range with their current `status`:
    * `Available` — unoccupied
    * `Occupied` — shows member name and guest count
    * `Closed` — taken out of service
4. Locate the lane to clear — confirm the occupant has vacated the physical lane
5. Tap the occupied lane → select **Force checkout**
6. Confirm the action

The kiosk calls `POST /v1/admin/lanes/{lane_id}/checkout`. The system:

* Sets `lanes.status = Available`, clears `current_member_id`, `guest_count`, and `checked_in_at`
* Writes a `Range-Checkout` entry to `activity_logs` with your `member_id` recorded as `actor_member_id`
* Advances the wait list: promotes the next `Waiting` entry to `Called`, sets `expires_at = called_at + 5 minutes`, and sends an **Amazon SNS** SMS to the next member in queue (if they have a `mobile_phone` on record)

**The kiosk returns `409 Conflict`** if the lane is not `Occupied` — `Available` and `Closed` lanes are rejected. This is expected; no action is needed.

---

## Procedure B — Force-checkout from the Admin Portal

Use this path when no kiosk is available but internet access is present.

1. Sign in to the **Admin Portal** with a Level 4+ account
2. Navigate to **Ranges → Occupancy**
3. Locate the range and lane to clear — confirm the occupant has vacated
4. Click **Force checkout** next to the occupied lane
5. Confirm the action

The Admin Portal calls the same `POST /v1/admin/lanes/{lane_id}/checkout` endpoint. The audit trail and wait-list advancement are identical to Procedure A.

---

## After force-checkout

* The lane immediately appears as `Available` in the RSO Dashboard and the Admin Portal occupancy view (next poll refresh)
* The `Range-Checkout` entry in `activity_logs` records the RSO's `actor_member_id` and timestamp for audit purposes
* If a wait-list entry exists, the next member is notified — the 5-minute window starts from the moment force-checkout completes
* If the range is being closed after an incident or emergency, proceed to close the range via **Ranges → Close range** (this sets `ranges.is_open = false` to prevent new check-ins)
