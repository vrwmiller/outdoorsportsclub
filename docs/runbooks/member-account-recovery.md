# Member Account Recovery

**Audience:** Webmaster (Level 6).

This runbook covers the procedure for restoring a member's access when they have lost access to their linked Google or Facebook social account. This is the "Un-Link" protocol described in `docs/design.md` Section 3.

> This procedure clears the member's `social_provider_id` so they can re-link a new social account on their next login. It does **not** delete the member record or any associated data.

---

## Prerequisites

* **Admin Portal** access with a Level 6 account
* Physical identity verification of the member (see Step 1)

---

## 1. Verify the member's identity

The member must present a government-issued photo ID **or** their physical Outdoor Sports Club badge to an **Administrator (Level 5+)** or **Webmaster (Level 6)** in person. Remote identity verification is not sufficient for this procedure.

Record:

* Member name (confirm against their record in the **Admin Portal**)
* The verification method used (badge, driver's licence, etc.)
* The date of the interaction

This record does not need to be entered into the system, but should be retained by the Webmaster for audit purposes (email, notebook, or signed form).

---

## 2. Clear the social provider link

1. Sign in to the **Admin Portal** with a Level 6 account
2. Navigate to **Members** and locate the member by name or member number
3. Click **Account recovery → Clear social login**
4. Confirm the action

The portal calls `PATCH /v1/admin/members/reset-auth` with the member's `member_id`. The Lambda clears `social_provider_id` in the **AWS Cognito** User Pool for that record.

**Returns `200 OK`** on success. The member's existing session (if any) will continue until their current Cognito access token expires (default: 1 hour). New login attempts using the old social account will fail immediately after the field is cleared.

---

## 3. Notify the member

Inform the member:

* Their old social login has been unlinked
* They should visit the **Member Portal** and log in with their **new** Google or Facebook account
* On first login with the new account, the system matches by email address and automatically re-links the profile

> The re-link works by email match. If the member's new social account uses a **different email address** than their record in `members.email`, contact the Webmaster immediately — the auto-link will fail and a manual email update will be needed before they attempt to log in.

---

## 4. Confirm re-link

After the member has logged in with their new social account:

1. In the **Admin Portal**, open the member's profile
2. Confirm that `social_provider_id` is populated and reflects the new social account
3. Confirm the member can access the **Member Portal** and their QR badge is visible

---

## Notes

* A cleared `social_provider_id` does **not** affect the member's `training_level`, `dues_paid_until`, or any other profile data — those fields are untouched.
* `activity_logs` does not record an explicit event for this operation; the timestamp of the `PATCH /v1/admin/members/reset-auth` call is the audit record.
* If a member reports they cannot log in but their `social_provider_id` is still populated, the issue is likely with their social account itself (password reset, 2FA, account suspension) — this procedure does not apply in that case.
