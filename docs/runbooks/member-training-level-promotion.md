# Member Training Level Promotion

**Audience:** Administrator (Level 5) or Webmaster (Level 6).

This runbook covers updating a member's `training_level` in the Admin Portal, including updating service hours for the Level 1 → 2 promotion. All level changes are explicit Administrator actions — no automated promotion occurs.

See `docs/design.md` Section 1 for the full RBAC schema and level progression diagram.

---

## Prerequisites

* **Admin Portal** access with a Level 5+ account
* The member's name or member number to look them up in the member list
* Confirmation that the promotion criteria have been met (see table below)

| Promotion | Criteria |
| :--- | :--- |
| Level 0 → Level 1 | Administrator discretion — new member accepted |
| Level 1 → Level 2 | 6 volunteer service hours completed (tracked manually) |
| Level 2 → Level 3 | Qualification training completed |
| Level 3 → Level 4 | RSO certification obtained |
| Level 4 → Level 5 | Administrator discretion |
| Level 5 → Level 6 | Administrator discretion |

---

## 1. Update service hours (Level 1 → Level 2 only)

Service hours are tracked manually. Before promoting a Level 1 member to Level 2, record their completed hours.

1. Sign in to the **Admin Portal** with a Level 5+ account
2. Navigate to **Members** and locate the member
3. Click **Edit** → **Service hours**
4. Enter the updated total (e.g., `6.00`)
5. Click **Save**

The portal calls `PATCH /v1/admin/members/{member_id}/service-hours`. A `Service-Hours-Update` entry is written to `activity_logs` with your account recorded as `actor_member_id`.

> Service hours are a running total, not a per-event value. Enter the new cumulative total, not an increment. Once `service_hours >= 6`, proceed to Step 2 to issue the level change — the two steps are intentionally separate to keep a human in the loop.

---

## 2. Promote the member's level

1. In the **Admin Portal**, navigate to **Members** and locate the member
2. Click **Edit** → **Training level**
3. Select the new level from the dropdown (0–6)
4. Review the change summary — confirm the member name, current level, and new level
5. Click **Confirm**

The portal calls `PATCH /v1/admin/members/{member_id}/level`. The system:

* Re-queries the member's current `training_level` from **Aurora** before applying the change (never from the JWT)
* Updates `members.training_level`
* Writes a `Level-Change` entry to `activity_logs` with:
  * `member_id` = the target member
  * `actor_member_id` = your account's `members.id`

**Returns `200 OK`** on success. The member's new level takes effect immediately on their next authenticated request — no session invalidation is required because `training_level` is always re-queried from the database, never read from the JWT.

---

## 3. Verify the change

1. In the **Admin Portal**, open the member's profile and confirm the new `training_level` is displayed
2. Optionally, check **Activity log** for a `Level-Change` entry recording the promotion with timestamp and your account as `actor_member_id`

---

## Notes

* **Demotion** follows the same steps — select a lower level in the dropdown. A demotion takes effect immediately; if the member is currently checked in to a range that their new level no longer qualifies for, the lane assignment remains open until they check out (the level gate applies at check-in, not retroactively to active sessions).
* **Level 6 accounts** can only be created by another Level 6 account.
* **Level changes cannot be undone via the UI.** If a level was set incorrectly, issue a corrective level-change call to restore the intended value — both entries remain in `activity_logs` for audit purposes.
