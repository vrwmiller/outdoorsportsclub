# Kiosk Provisioning

**Audience:** Webmaster (Level 6).

This runbook covers provisioning a new kiosk tablet, verifying it is active, and revoking a lost or replaced device. All steps require an active **Admin Portal** session authenticated as a **Webmaster (Level 6)** account.

See `docs/design.md` Section 2 for the full pairing sequence and `devices` table schema.

---

## Prerequisites

* **Admin Portal** access with a Level 6 account
* The kiosk tablet is powered on, connected to the facility network, and has the Outdoor Sports Club application installed and open
* The `range_id` for the range this kiosk will serve (visible in the **Admin Portal** range list)

---

## 1. Generate a pairing code

1. Sign in to the **Admin Portal** with a Level 6 account
2. Navigate to **Devices → Provision new kiosk**
3. Enter:
    * **Location tag** — human-readable name for this tablet (e.g., `Skeet-Trap-1`)
    * **Range** — select the range this kiosk serves from the dropdown
4. Click **Generate pairing code**
5. The portal calls `POST /v1/admin/devices/pairing-code` and displays a short alphanumeric code with a **15-minute expiry**

> The pairing code is single-use and expires after 15 minutes. If it expires before the tablet completes pairing, repeat this step to generate a new code — the old device row is rejected automatically if a new code is generated for the same `location_tag`.

---

## 2. Pair the tablet

Hand the pairing code to the technician setting up the tablet (or enter it yourself if you have physical access).

On the tablet:

1. Open the Outdoor Sports Club app
2. Navigate to **Settings → Pair this device** (visible only before pairing is complete)
3. Enter the pairing code exactly as displayed
4. Tap **Pair**

The tablet calls `POST /v1/devices/pair` with the pairing code. On success:

* The server generates a unique `device_token`, stores its salted hash in `devices.device_token`, sets `status = Active`, and clears the pairing code
* The raw token is returned to the tablet once and stored in the tablet's secure storage — it is never displayed or transmitted again
* The tablet proceeds to the **Idle** kiosk screen

---

## 3. Verify the device is active

In the **Admin Portal**:

1. Navigate to **Devices**
2. Confirm the new device appears with:
   * `status = Active`
   * Correct `location_tag` and range assignment
   * `pairing_code` column empty (cleared on successful pairing)

On the tablet, confirm the **Idle** screen is displayed and a test QR scan returns a valid response.

---

## 4. Revoke a lost, stolen, or replaced device

If a tablet is lost, stolen, or taken out of service, revoke it immediately so any outstanding device token is rejected on the next request.

1. Sign in to the **Admin Portal** with a Level 6 account
2. Navigate to **Devices** and locate the device by `location_tag`
3. Click **Revoke**
4. Confirm the revocation

The portal sets `devices.status = Revoked`. The next API call from that tablet returns `403 Forbidden` — the token is invalid and the kiosk cannot be used for check-ins until a new device is provisioned.

> Revoking a device does **not** affect any open lane assignments at that range. Existing check-ins remain in `activity_logs`; RSOs may still force-checkout occupied lanes from another kiosk on the same range or from the Admin Portal. See the [RSO force-checkout runbook](rso-force-checkout.md).

---

## 5. Replace a revoked device

A revoked `device_token` cannot be reactivated. To bring a replacement tablet online:

1. Follow **Step 1** to generate a new pairing code — use the same `location_tag` if this is a direct hardware replacement
2. Follow **Steps 2 and 3** on the replacement tablet
3. Confirm the revoked device row is no longer active (it remains in `devices` with `status = Revoked` for audit purposes)
