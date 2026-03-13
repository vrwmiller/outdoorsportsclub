# design.md

## 1. Training-Centric Access Schema (RBAC)

The system's **Role-Based Access Control (RBAC)** is driven by the user's verified "Training Level." This serves as a digital gatekeeper at the **Member Portal**, the **Admin Portal**, and the **Mobile Kiosks**.

The application has four surfaces. The **Home Page** is the club's primary public-facing interface and the entry point for all website visitors. After login, users are routed to the **Member Portal** (Level 0–3) or the **Admin Portal** (Level 4–6). The **Kiosk View** is the default full-screen interface served to paired range tablets and is accessed exclusively via Device Token — it is entirely separate from the website login flow.

| Level | Designation | Digital Permissions | Range & System Logic |
| :--- | :--- | :--- | :--- |
| **0** | **Guest** | Waiver & Payment | Must pay guest fee and sign digital form at Kiosk. |
| **1** | **Probationary** | Range Access | Restricted range access pending completion of 6 volunteer service hours (tracked manually by Administrator). |
| **2** | **Basic Member** | General Access | Unlocks check-in for basic facilities (Skeet, Trap, Archery). |
| **3** | **Qualified** | Specialized Access | Verified Qualification unlocks specialized Rifle/Pistol ranges. |
| **4** | **RSO / Instructor** | Range Ops | Can "Open/Close" ranges and override guest limits. |
| **5** | **Administrator** | Business Oversight | **Full Business Access:** Finance, Database, and Rules. |
| **6** | **Webmaster** | **Technical Oversight** | **Full System Access:** API logs, Device Pairing, and Recovery. |

## 2. Kiosk Identity & Device Provisioning (AWS)

To ensure high-speed check-ins and eliminate the security risks of social login on shared tablets, the system utilizes **Secure Device Pairing**:

* **Pairing Workflow:** A **Webmaster (Level 6)** initiates device provisioning via the Admin Portal, which generates a short-lived **Pairing Code**. The Webmaster hands the code to the technician configuring the tablet; the tablet uses the code to complete pairing and receive its Device Token.
* **Kiosk Token:** Once paired, the server issues a unique **Device Token** stored in the tablet's secure storage. The tablet then functions as a trusted appliance.
* **Revocation:** If a tablet is lost or stolen, the **Webmaster** sets the device's `status` to `Revoked` in the `devices` table via the Admin Portal. The next API request from that tablet will be rejected immediately.

## 3. Member Identity & Recovery Protocol

* **Personal Devices:** Members use **Social Login (Google/Facebook)** via **AWS Cognito** on their own phones/computers to access the portal and pay annual dues.
* **Account Recovery (The "Un-Link" Protocol):** If a member loses access to their social account, the **Webmaster (Level 6)** executes the following:
    1. **Identity Verification:** Member presents their physical badge/ID to an **Admin** or **Webmaster**.
    2. **Token Reset:** The **Webmaster** clears the `social_provider_id` in the **Cognito User Pool** for that record.
    3. **Re-Link:** On the next login attempt, the member uses their *new* social account; the system recognizes the email/ID match and re-binds the profile.
* **The Digital Badge:** The portal generates a unique **Member QR Badge**. This badge is the "Key" that the tokenized Kiosk recognizes to log a check-in or verify a Training Level.

## 4. Operational Track (Mobile Kiosk)

### Physical kiosk model

Staffed ranges (Rifle/Pistol, Skeet/Trap, and staffed Archery and Air Rifle) each have 2–3 tablet kiosks. Unstaffed ranges (outdoor Archery and indoor Air Rifle when not staffed) do not have kiosks — no check-in flow applies.

The kiosk handoff model — whether the RSO holds the tablet and hands it to arriving users, or the tablet is fixed-mount and self-serve — is an **open design question (#13)**. Both models are supportable by the same underlying check-in flow; the difference is physical deployment and the violation-clearing mechanism.

### Kiosk states

| State | Description |
| :--- | :--- |
| **RSO Dashboard** | Default view. Displays lane occupancy for this kiosk's range: each lane shows `Available` or the name/member number of the assigned occupant and their guest count. Lane state is re-fetched after every check-in and check-out transaction, and polled every 30 seconds between transactions. |
| **Check-in flow** | Initiated by RSO. Member scans QR Badge; system validates `training_level`, waiver, dues, and guest count. |
| **Guest add-on** | After the member's lane is assigned, the kiosk prompts: "Add guests? (0 / 1 / 2)." For each guest, the RSO enters a name and phone number; the kiosk looks up the guest in the `guests` table. If a valid waiver is on file, no re-signing is required. If no record exists or the waiver has expired, the kiosk captures a waiver acknowledgement before proceeding. The annual visit count for this guest-member combination is then checked — if the limit has been reached (≥ 2 visits in the current calendar year), the guest is turned away (`403 Forbidden`; no RSO override applies to this rule). For guests that pass all checks, the kiosk presents a payment screen. Either the guest or the sponsoring member may tap to pay. Guests share the member's lane. |
| **Violation alert** | Displayed when check-in fails a rule (e.g., guest limit exceeded, waiver expired, insufficient level). The user cannot dismiss this screen — only the RSO can clear it by either resolving the issue or denying entry. |
| **Lane assignment** | After check-in (and optional guest add-on) is complete, the assigned lane and guest count are confirmed on screen. |
| **Check-out flow** | RSO-initiated or user-initiated. Member scans QR Badge; open lane assignment (including all guests on that lane) is closed and the lane returns to `Available`. |

### Flow rules

* **The "Safety Gate":** Automated blocking of check-ins for members with insufficient `training_level` for a specific range.
* **Mandatory Check-Out:** Range users must check out before leaving. Check-out closes the lane assignment (including all guests) and logs a `Range-Checkout` event.
* **Violation lock:** A failed check-in locks the screen in violation state. The RSO resolves — approve an override where policy allows, or deny entry. Only Level 4+ can clear a violation alert.
* **Lane assignment:** Each member check-in assigns one available lane. Member and all their guests share that lane. If no lanes are available, check-in is blocked.
* **Guest accompaniment:** Guests must be physically present with and accompanied by their sponsoring member. A guest cannot arrive independently — there is no guest-only entry flow. The guest add-on step at the kiosk (after the member's lane is assigned) is the only entry point for guest registration and payment.
* **Guest sponsorship:** A member may bring a maximum of **2 guests per range visit**. The limit is enforced per range — a member may not bring more than 2 guests on the same range at the same time. Guest count is stored in `lanes.guest_count` and checked at check-in.
* **Guest check-in order:** The member checks in first and is assigned a lane. The kiosk then offers the guest add-on step (0, 1, or 2 guests). Each guest requires a waiver acknowledgement and a fee payment via **Stripe Terminal** (Tap to Pay). Either the guest or the sponsoring member may pay.
* **Cashless Guest Fees:** Integrated "Tap-to-Pay" (NFC) via mobile tablets at the range, powered by the **Stripe Terminal SDK**. No additional card reader hardware is required — the tablet's built-in NFC chip acts as the payment terminal.
* **Consumable Sales:** Members and guests may purchase consumables (e.g., targets, canned soda, coffee) at the kiosk. Each transaction is recorded in the `consumable_purchases` table with full line-item detail. Payment is processed via **Stripe Terminal SDK** (Tap to Pay). **Known Limitation:** There is no reliable physical process to verify that recorded quantities match items actually dispensed; the system records what is entered at the kiosk but cannot enforce inventory accuracy.
* **Time-Bound Waivers:** Automated re-signing triggers for Safety Waivers based on 1-year expiration logic.
* **Tablet Hardware Requirement:** Kiosk tablets **must have an accessible NFC chip** to support Tap to Pay. Most modern Android tablets and iPads qualify. Budget or older Android tablets may omit NFC — verify hardware specs before purchasing.

### Offline operation

If internet connectivity is lost, the kiosk must continue to support member check-in and check-out using a locally cached dataset. Guest payment (Stripe Terminal) requires connectivity and cannot be processed offline. See **Open Design Question #10** for the offline architecture decisions.

## 5. Data Schema (Amazon Aurora Serverless v2)

The database utilizes a relational model (PostgreSQL) with **Row-Level Security (RLS)**. This ensures members can only access their own profiles, while Level 4–6 users have elevated visibility for range safety and system maintenance.

### **5.1 Table: `members`**

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | UUID (PK) | Internal unique identifier for all relational joins. |
| `member_num` | TEXT (Unique) | Physical badge number encoded in the **QR Badge**. |
| `email` | TEXT (Unique) | Primary contact and anchor for Social Login. |
| `training_level` | INT (0-6) | **The Master Key:** Determines base permissions. |
| `social_provider_id` | TEXT (Nullable) | Linked Google/Facebook ID (Cleared during **Recovery**). |
| `service_hours` | DECIMAL(5,2) | Running total for **Level 1** promotion tracking. |
| `waiver_signed_at` | TIMESTAMP | Used to calculate the 1-year automated expiration. |
| `dues_paid_until` | DATE | Date-based flag for membership standing. |
| `home_phone` | TEXT (Nullable) | Home telephone number. |
| `mobile_phone` | TEXT (Nullable) | Mobile number in E.164 format (e.g., `+15551234567`); validated/normalized for **Amazon SNS** delivery of SMS range alerts. |

### **5.2 Table: `ranges`**

All physical ranges have a row in this table, regardless of whether they are currently staffed. The `ranges` table is the authoritative source for open/close state and access requirements. Unstaffed ranges (outdoor Archery, Air Rifle when unstaffed) do not have kiosk devices assigned to them, but they still appear here so that `min_training_level` and `is_open` are centrally managed for all ranges.

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | UUID (PK) | Unique range identifier. |
| `name` | TEXT (Unique) | Human-readable range name (e.g., `Rifle-Pistol`, `Skeet-Trap`). |
| `is_open` | BOOLEAN | `true` when the range is open for check-in. Closing a range prevents new check-ins; existing occupants are not force-cleared — the RSO conducts a physical closing procedure to ensure the range is vacated before locking the gate. |
| `min_training_level` | SMALLINT (0-6) | Minimum `training_level` required to check in at this range. Applied at check-in time; authoritative value always queried from this table, never from the device or JWT. |

**Initial seed data:**

| `name` | `is_open` | `min_training_level` |
| :--- | :--- | :--- |
| `Rifle-Pistol` | `false` | 1 |
| `Skeet-Trap` | `false` | TBD |
| `Air-Rifle` | `false` | TBD |
| `Indoor-Archery` | `false` | TBD |
| `Outdoor-Archery` | `false` | TBD |

*Names are provisional — confirm with club leadership before the seed migration is written. All ranges seed as closed. `min_training_level` values TBD.*

### **5.3 Table: `devices` (Kiosks)**

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | UUID (PK) | Unique hardware ID. |
| `device_token` | TEXT (Nullable) | Salted hash of the secret used for **Kiosk-to-API** authentication. Null until pairing is complete. |
| `location_tag` | TEXT | Human-readable name (e.g., `Skeet-Trap-1`). |
| `range_id` | UUID (FK) | FK to `ranges.id`. Determines which range this kiosk serves; used to look up `is_open` and `min_training_level` at check-in. |
| `status` | TEXT | `Pending-Pairing`, `Active`, `Revoked` |
| `pairing_code` | TEXT (Nullable) | Short-lived alphanumeric code generated by the Admin Portal during device provisioning. Single-use; cleared on successful pairing. Null for `Active` and `Revoked` devices. |
| `pairing_code_expires_at` | TIMESTAMP (Nullable) | Expiry time for the pairing code (15-minute TTL). Requests with an expired code are rejected. |

### **5.4 Table: `lanes`**

Each lane belongs to a range and tracks current occupancy. The `devices` table links kiosks to ranges; lanes belong to ranges, not to individual kiosk tablets.

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | UUID (PK) | Unique lane identifier. |
| `range_id` | UUID (FK) | FK to `ranges.id`. Replaces the former `range_tag` TEXT column. |
| `lane_number` | SMALLINT | Lane number within the range (e.g., 1–17 for Rifle-Pistol). |
| `status` | TEXT | `Available`, `Occupied` |
| `guest_count` | SMALLINT | Number of guests currently sharing this lane with the sponsoring member (0–2). Always 0 when `status` is `Available`. |
| `current_member_id` | UUID (FK, Nullable) | FK to `members.id`; set on check-in, cleared on check-out. Nullable only when the lane is `Available`. Guests must be accompanied by a member — the lane is assigned to the sponsoring member's ID for the duration of the guest's occupancy. A null value always means the lane is unoccupied. |
| `checked_in_at` | TIMESTAMP (Nullable) | Time the lane was last claimed. |

**Constraints and indexes:**

* `UNIQUE (range_id, lane_number)` — no two lanes can share the same number within a range.
* `CHECK (status IN ('Available', 'Occupied'))`
* `CHECK (guest_count BETWEEN 0 AND 2)`
* `CHECK (status = 'Available' AND current_member_id IS NULL AND guest_count = 0 OR status = 'Occupied' AND current_member_id IS NOT NULL AND guest_count BETWEEN 0 AND 2)` — enforces consistency between occupancy state, sponsoring member, and guest count.
* `INDEX ON (range_id, status)` — supports finding available/occupied lanes for a range.
* `INDEX ON (current_member_id)` — supports finding the lane a member is currently occupying.

### **5.5 Table: `activity_logs`**

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | BIGINT (PK) | High-volume log ID. |
| `member_id` | UUID (FK) | Reference to the `members` table. |
| `device_id` | UUID (FK) | Reference to the `devices` table. |
| `activity_type` | TEXT | `Range-Checkin`, `Range-Checkout`, `Guest-Payment`, `Waiver-Signed`, `Level-Change` |
| `lane_id` | UUID (FK, Nullable) | Lane associated with the activity. Populated for `Range-Checkin`, `Range-Checkout`, and `Guest-Payment` events so that payments can be tied to a specific range visit and lane for reconciliation and dispute resolution; null only for `Waiver-Signed` events with no lane context. |
| `stripe_payment_intent_id` | TEXT (Nullable) | Stripe Payment Intent ID; populated for `Guest-Payment` events only and linked to the lane/visit via `lane_id`. |
| `guest_id` | UUID (FK, Nullable) | FK to `guests.id`; populated for `Guest-Payment` and `Waiver-Signed` events involving a guest. Null for all other activity types. |
| `timestamp` | TIMESTAMP | Audit-ready event time. |

### **5.6 Table: `training_level_policies`**

One row per training level. Stores scalar constraints enforced automatically at check-in. Admin-editable without a schema migration.

| Column | Type | Description |
| :--- | :--- | :--- |
| `training_level` | SMALLINT (PK, 0-6) | The member level this policy applies to. |
| `max_guests` | SMALLINT | Maximum number of guests a member at this level may bring per range visit. `0` means guests are not permitted. |

**Seed data:**

| `training_level` | `max_guests` | Notes |
| :--- | :--- | :--- |
| 0 | 0 | Guest — cannot sponsor guests |
| 1 | 0 | Probationary — guests not permitted |
| 2 | TBD | Standard — TBD |
| 3 | 2 | Qualified — up to 2 guests per visit |
| 4 | 2 | RSO/Instructor |
| 5 | 2 | Senior RSO |
| 6 | 2 | Webmaster |

*Level 2 `max_guests` to be confirmed. All other values are known.*

Enforced at check-in by querying `training_level_policies.max_guests` for the member's level and comparing against the requested guest count. Exceeding the limit triggers a violation alert (see ODQ #11).

### **5.7 Table: `consumable_purchases`**

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | UUID (PK) | Unique purchase record. |
| `member_id` | UUID (FK, Nullable) | Reference to `members` table; nullable for guest purchases. |
| `device_id` | UUID (FK) | Kiosk where the purchase was recorded. |
| `item_name` | TEXT | Name of the consumable (e.g., `targets`, `soda`, `coffee`). |
| `quantity` | INT | Number of units purchased. |
| `unit_price` | DECIMAL(6,2) | Price per unit at time of sale. |
| `total` | DECIMAL(8,2) | `quantity × unit_price`; computed at transaction time. |
| `stripe_payment_intent_id` | TEXT | Stripe Payment Intent ID for reconciliation and dispute resolution. |
| `timestamp` | TIMESTAMP | Audit-ready event time. |

### **5.8 Table: `guests`**

A persistent identity record for non-member visitors. Created on first visit; reused on subsequent visits so a valid waiver on file does not need to be re-signed.

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | UUID (PK) | Unique guest identifier. |
| `first_name` | TEXT | Guest first name. |
| `last_name` | TEXT | Guest last name. |
| `phone` | TEXT | Contact phone in E.164 format. Part of the composite lookup key. |
| `email` | TEXT | Guest email address. Part of the composite lookup key; also used for waiver delivery or future notifications. |
| `waiver_signed_at` | TIMESTAMP (Nullable) | Timestamp of the most recent waiver signing. Null until completed at the kiosk on first visit. Checked against the 1-year expiration rule on each visit. |
| `waiver_s3_key` | TEXT (Nullable) | S3 object key for the signed waiver document; stored with S3 Object Lock (Compliance Mode) consistent with member waivers. |

**Constraints and indexes:**

* `UNIQUE (first_name, last_name, phone, email)` — lookup composite key.
* `INDEX ON (last_name, phone, email)` — kiosk lookup during the guest add-on step.

### **5.9 Table: `guest_visits`**

One row per range visit per guest. Used to enforce the annual visit limit: a guest-member combination may visit at most twice per calendar year. Guests that reach the limit are turned away — no RSO override applies to this rule.

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | UUID (PK) | Unique visit record. |
| `guest_id` | UUID (FK) | FK to `guests.id`. |
| `member_id` | UUID (FK) | FK to `members.id` — the sponsoring member for this visit. |
| `range_id` | UUID (FK) | FK to `ranges.id` — the range visited. |
| `lane_id` | UUID (FK, Nullable) | FK to `lanes.id` — the lane assigned for this visit. |
| `visited_at` | TIMESTAMP | Visit timestamp; used to scope the annual limit check to the current calendar year. |
| `stripe_payment_intent_id` | TEXT (Nullable) | Stripe Payment Intent ID for the guest fee charged on this visit. Duplicated here for direct reconciliation without joining to `activity_logs`. |

**Annual limit check:** Query `guest_visits` using a timestamp range rather than `EXTRACT(YEAR …)` so the `(guest_id, member_id, visited_at)` index is used:

```sql
SELECT COUNT(*)
FROM guest_visits
WHERE guest_id  = $1
  AND member_id = $2
  AND visited_at >= date_trunc('year', now() AT TIME ZONE 'UTC')
  AND visited_at  < date_trunc('year', now() AT TIME ZONE 'UTC') + INTERVAL '1 year';
```

If the count is ≥ 2, the kiosk returns `403 Forbidden`. All times are stored and compared in UTC. A `guest_visits` row is inserted only after payment is confirmed. To prevent a race condition where two simultaneous guest-payment requests both pass the count check, the check and insert must execute within a single **serializable transaction** (or use `SELECT … FOR UPDATE` on the sponsoring member's lane record to serialize concurrent check-ins for the same member).

**Indexes:**

* `INDEX ON (guest_id, member_id, visited_at)` — annual count query.
* `INDEX ON (member_id)` — sponsor history lookup.

## 6. Infrastructure & Security (AWS)

* **Storage:** Signed waivers are stored in **Amazon S3** with **S3 Object Lock** (Compliance Mode) to prevent tampering or accidental deletion.
* **Notifications:** Urgent safety alerts or range closures are pushed via **Amazon SNS** (SMS) to ensure reach to 100% of members.
* **Zero-Trust Security:** Data is encrypted at rest and in transit via **AWS KMS**; no raw credit card data is ever stored on Club-managed systems.
* **Authorization invariant — `training_level`:** Every Lambda that gates access by training level **must re-query `training_level` from Aurora** on every request. It must never be read from the Cognito JWT claim. The JWT is used only to identify the caller (via `sub`); the authoritative level is always the database row. A member's level can be revoked between token issuance and token expiry — reading the claim would miss that change.

## 7. API Outlines (AWS-Native / RESTful)

The API layer is built using **AWS Lambda** and **Amazon API Gateway**, integrated via **AWS Amplify**.

### **7.1 Member Portal Operations**

* **`GET /v1/members/me`** (**Authenticated member**, Level 1–6)
  * **Logic:** Returns the authenticated member's own profile. `member_id` resolved from Cognito JWT `sub`; all fields queried from Aurora — never from the JWT claims.
  * **Returns:** `200 OK` with `{ member_num, training_level, service_hours, dues_paid_until, waiver_signed_at, mobile_phone }`.

* **`GET /v1/members/me/badge`** (**Authenticated member**, Level 1–6)
  * **Logic:** Returns the member's `member_num` for QR code display in the Member Portal. The frontend renders the `member_num` as a QR code; the kiosk scans and resolves it via `POST /v1/kiosk/check-in`.
  * **Returns:** `200 OK` with `{ member_num }`.

### **7.2 Kiosk Operations**

* **`GET /v1/kiosk/range/lanes`** (**Device Token** authenticated)
  * **Logic:** Returns current lane occupancy for the kiosk's own range (resolved from the Device Token's `range_id`). Used by the RSO Dashboard for the initial load, post-transaction re-fetch, and the 30-second background poll between transactions.
  * **Returns:** `200 OK` with `{ range_id, name, is_open, lanes: [{ lane_id, lane_number, status, current_member_id, member_num, guest_count, checked_in_at }] }`. `member_num` and `checked_in_at` are `null` when `status` is `Available`.

* **`POST /v1/kiosk/check-in`**
  * **Logic:** Triggered by a QR scan. Resolves the device's `range_id`, then validates: (1) `ranges.is_open = true`; (2) member `training_level ≥ ranges.min_training_level`; (3) waiver not expired; (4) dues current; (5) requested guest count ≤ `training_level_policies.max_guests` for this member's level; (6) an available lane exists. All values queried from Aurora via the **RDS Data API** — never from the JWT or device record directly.
  * **Returns:** `200 OK` (Access Granted) or `403 Forbidden` (e.g., "Range closed", "Level 3 Required", "Guests not permitted at this level").

* **`POST /v1/kiosk/check-out`**
  * **Logic:** Triggered by a QR scan at range exit. Validates an active open `Range-Checkin` exists for the member on that device; writes a `Range-Checkout` record to `activity_logs`.
  * **Returns:** `200 OK` (Check-Out Logged) or `404 Not Found` (no open check-in on record).

* **`POST /v1/kiosk/guest-payment`**
  * **Logic:** Handles the full guest add-on flow for a single guest: (1) look up guest by `first_name`, `last_name`, and `phone` in `guests` — create a new record if not found; (2) check `guests.waiver_signed_at` — prompt waiver capture at the kiosk if no record exists or the waiver has expired; (3) query `guest_visits` for this guest-member combination in the current calendar year — if count ≥ 2, return `403 Forbidden` (hard block; no RSO override applies); (4) process the guest fee via **Stripe Terminal SDK** (Tap to Pay on tablet NFC); (5) insert a `guest_visits` row; (6) create an `activity_logs` entry with `guest_id` populated.
  * **Returns:** `200 OK`, `403 Forbidden` (annual limit reached), or `402 Payment Required` (Stripe failure).

* **`POST /v1/kiosk/consumable-purchase`**
  * **Logic:** Records one or more line items (item name, quantity, unit price) to `consumable_purchases`; processes payment via **Stripe Terminal SDK** (Tap to Pay). `member_id` is optional — omit for anonymous guest purchases.
  * **Returns:** `200 OK` (Purchase Recorded) or `402 Payment Required` (Stripe payment failure).

### **7.3 Administrative & Recovery**

* **`GET /v1/admin/ranges/occupancy`** (**Level 4+** RSO)
  * **Logic:** Returns current lane occupancy for all ranges. Each range entry includes `range_id`, `name`, `is_open`, and a list of lanes with their `status`, `lane_number`, `current_member_id` (if occupied), and `guest_count`. Intended for the supervisory cross-range view in the **Admin Portal** and mobile web. Polled by the client at a suitable interval (e.g., 30 seconds). No push mechanism required.
  * **Returns:** `200 OK` with an array of range occupancy objects.

* **`PATCH /v1/admin/members/reset-auth`** (**Level 6** **Webmaster** Only)
  * **Logic:** Clears the `social_provider_id` in the **Cognito User Pool** for the specific `member_id`.

* **`POST /v1/admin/devices/pairing-code`** (**Level 6** **Webmaster** Only)
  * **Logic:** Creates a new device row in `devices` (status `Pending-Pairing`) with a cryptographically random alphanumeric pairing code and a 15-minute expiry. The `location_tag` and `range_id` are set at this point. The Admin Portal displays the generated code for the Webmaster to hand to the technician configuring the tablet. A device row with an unexpired code for the same `location_tag` is rejected — preventing duplicate device creation.
  * **Returns:** `201 Created` with `{ device_id, pairing_code, expires_at }`.

* **`POST /v1/devices/pair`** (Unauthenticated — identified by Pairing Code)
  * **Logic:** Called by the tablet during initial setup. Validates the supplied `pairing_code` against `devices` — rejects if not found, already used, or expired. On success: generates a `device_token`, stores its salted hash in `devices.device_token`, sets `status = Active`, and clears `pairing_code` and `pairing_code_expires_at`. Returns the raw token to the tablet, which stores it in secure storage. This is the only time the raw token is transmitted.
  * **Returns:** `200 OK` with `{ device_token }` or `400 Bad Request` (invalid/expired code).

* **`PATCH /v1/admin/ranges/{range_id}/status`** (**Level 4+** RSO)
  * **Logic:** Sets `ranges.is_open` to `true` or `false`. Callable from both the **Admin Portal** and the **Kiosk View** RSO dashboard. Closing a range does not force-clear active lanes — the RSO conducts a physical closing procedure to verify the range is vacated before locking the gate. The RSO dashboard continues to display current lane occupancy while `is_open = false` to support this procedure.
  * **Returns:** `200 OK` or `403 Forbidden`.

* **`POST /v1/admin/lanes`** (**Level 4+** RSO)
  * **Logic:** Creates a new lane for a range. `range_id` and `lane_number` required.
  * **Returns:** `201 Created` or `409 Conflict` (duplicate lane number).

* **`PATCH /v1/admin/lanes/{lane_id}`** (**Level 4+** RSO)
  * **Logic:** Updates lane status or disables a lane. Used for range reconfiguration without requiring a DB migration.
  * **Returns:** `200 OK` or `404 Not Found`.

* **`PATCH /v1/admin/members/{member_id}/level`** (**Level 5+** Administrator)
  * **Logic:** Updates `members.training_level` for the specified member. Requires `training_level` (0–6) in the request body. Re-queries the current level from Aurora before applying the change and writes an `activity_logs` entry with `activity_type = 'Level-Change'`. No automated promotion logic — all level changes are explicit Administrator actions.
  * **Returns:** `200 OK` or `403 Forbidden`.

## 8. High Availability, Multi-Region & Disaster Recovery

### Design principle: variable region count

The infrastructure is designed from the start to support any number of active regions. Region count is a **deployment-time parameter** — adding or removing a region requires a configuration change, not an architectural change. Initial deployment uses a single primary region. Multi-region active-active is enabled when the system is ready for production.

This principle is especially critical for payment processing: Stripe Terminal transactions must not be lost or duplicated during a regional failure.

### Regional stack

Each active region runs a complete, independent copy of:

* **API Gateway** — regional endpoint (not edge-optimised)
* **AWS Lambda** — all function code deployed identically per region
* **Amazon Aurora Serverless v2** — member of a **Global Database** cluster; one writer region, N reader regions; automatic failover promotes a reader to writer in under 60 seconds
* **Amazon S3** — waiver bucket with **Multi-Region Access Point (MRAP)** and **S3 Cross-Region Replication (CRR)** to all active region buckets; Object Lock preserved across replicas
* **AWS KMS** — multi-region keys (`mrk-` prefix) replicated to each active region; same key material, independent key ARNs per region
* **AWS Secrets Manager** — secrets replicated to each active region via Secrets Manager multi-region replication
* **AWS Cognito** — single User Pool in the primary region; regional Lambda@Edge or API Gateway endpoints proxy auth to the primary pool

### Traffic routing

* **Amazon Route 53** with **latency-based routing** or **failover routing** directs traffic to the nearest healthy regional API Gateway endpoint
* **Route 53 Health Checks** monitor each regional endpoint; unhealthy regions are automatically removed from DNS within ~30 seconds
* The Next.js frontend (Amplify hosting) is globally distributed via CloudFront — no change needed per region

### Deployment model

| Phase | Region count | Configuration |
| :--- | :--- | :--- |
| Development (`dev` stack, `us-east-1`) | 1 | `RegionList: us-east-1` — separate stack from prod, no PII |
| Production launch | 1 (primary) | `RegionList: us-east-1` |
| Multi-region active-active | 2 | `RegionList: us-east-1,us-east-2` — Northern Virginia and Ohio; both regions actively serve traffic, with Ohio as the failover target if Northern Virginia is unavailable |

All CloudFormation stacks accept a `RegionList` parameter. Cross-region resources (Aurora Global Database secondary clusters, KMS replica keys, S3 CRR rules, Secrets Manager replicas) are conditionally created: if `RegionList` has only one entry, none of the replication resources are provisioned.

### Non-production environment

The `dev` environment is a **completely separate CloudFormation stack** from `prod`. It shares no AWS resources, no data, and no secrets with production.

**Privacy compliance requirement:** The `dev` database must never contain real member data. This is required for compliance with GDPR (EU) and CCPA (California). All test data must be synthetically generated. If a production data restore is ever needed for debugging, it must be anonymised before import — names, email addresses, phone numbers, and `social_provider_id` values must be replaced with synthetic values.

| Setting | `dev` | `prod` |
| :--- | :--- | :--- |
| Aurora min/max ACU | 0.5 / 2 | 2 / 16 |
| S3 Object Lock mode | Governance (deletable by admin) | Compliance (7-year, locked) |
| AWS Backup Vault Lock | Off | Compliance mode |
| Backup retention | 7 days | 35 days |
| Stripe keys | Test-mode secret (`osc/dev/stripe-key`) | Live-mode secret (`osc/prod/stripe-key`) |
| Cognito User Pool | Separate pool; no real member accounts | Production pool |
| `RegionList` | `us-east-1` only | `us-east-1` (or more) |
| Real PII permitted | **Never** | Yes — protected by RLS and KMS |

The `dev` stack uses the same CloudFormation templates as `prod`, with `Environment: dev` passed as a parameter to select reduced-cost resource tiers and relaxed retention settings.

### Multi-region operational risk: configuration drift

Each region runs an independent copy of the stack. Configuration drift — where secrets, environment variables, Lambda code versions, or IAM policies diverge between regions — is a real operational risk in active-active deployments. Mitigations:

* All per-region configuration is declared in CloudFormation parameters and sourced from the same template; no manual console changes in production.
* Secrets Manager multi-region replication keeps secrets in sync automatically; secret rotation must be applied to the primary and allowed to replicate before it takes effect in secondary regions.
* Automated failover testing must validate that the promoted secondary region is behaviorally identical to the primary — including Stripe key, Cognito configuration, and KMS key access.

### Backup & point-in-time recovery

* **Aurora PITR:** 35-day continuous backup window; restore to any second
* **AWS Backup:** Daily snapshot at 02:00 UTC; 35-day retention; cross-region copy to every region in `RegionList`
* **AWS Backup Vault Lock:** Compliance mode on `prod` vaults only — snapshots cannot be deleted before retention expires; Vault Lock is **not** enabled on `dev`

### The "Red Button" procedure

In a full primary-region failure with active-active enabled: **Aurora Global Database** fails over and promotes a reader cluster in a secondary region to writer, and **Route 53** updates DNS to route traffic to the healthy regional endpoint. In single-region mode: the **Webmaster** deploys the stack to a new region using the IaC parameters and restores Aurora from **AWS Backup** or an Aurora point-in-time restore/snapshot. Target RTO: under 60 minutes from a cold start.

## 9. Architecture Decisions — Frontend Framework

**Outdoor Sports Club** uses **Next.js** for the frontend. The short rationale and guidance below explain why Next.js was chosen, why a full Django monolith was not selected, and when each option is appropriate.

Why Next.js was chosen:

* **Developer experience:** First-class TypeScript + React support, component re-use, and fast iteration for UI-focused teams.
* **Performance & SEO:** Built-in SSR/SSG/ISR options enable fast first paint and SEO for public/member pages.
* **Global distribution:** Static assets and pre-rendered pages are CDN-friendly via **AWS Amplify Gen 2** hosting and **Amazon CloudFront** with minimal infra overhead.
* **Incremental adoption:** Pages can be static, client-rendered, or server-rendered as needed without a large rewrite.
* **Serverless alignment:** Keeps the backend as small Lambda functions while letting the frontend be optimized for the edge/CDN.

Why Django was not chosen:

* **Monolithic pattern:** Django favors a server-rendered, monolithic architecture (templates, ORM, admin) that would couple frontend and backend lifecycle.
* **Operational weight:** Running a full Django app for a mostly static or CDN-served frontend increases operational complexity compared with static/SSR hosting.
* **Developer mismatch:** For a team centered on React/TypeScript, Django adds a cross-language integration surface and reduces frontend DX.

When to prefer Next.js:

* Teams focused on React/TypeScript who want component-driven development and CDN-first performance.
* Sites needing SEO or mixed static/dynamic rendering with simple serverless APIs.

When to prefer Django on other projects:

* For Outdoor Sports Club, the frontend framework is a locked decision: **Next.js** hosted via **AWS Amplify Gen 2** — Django is not an option for this implementation.
* For other projects, Django may be preferred for a Python-first monolith with deep server-side business logic, complex DB transactions, or where the built-in Django Admin is required for model management.
* For other projects, Django may also suit teams that prefer a single-language (Python) stack and where server-side rendering is the primary rendering model.

## 10. Architecture Decisions — External Review Findings

An independent architectural review was conducted against the design documented here. The following records which recommendations were accepted, rejected, or deferred, and why.

### Resolved: Ranges table and lane management (ODQ #5 and ODQ #12)

The review independently confirmed the need for a `ranges` table. Both questions are now resolved — see Section 5 for the full schema.

* A `ranges` table (Section 5.2) is the authoritative source for open/close state and `min_training_level` per range. `min_training_level` moves from `devices` to `ranges`.
* `lanes.range_tag` (TEXT) is replaced by `lanes.range_id` (UUID FK to `ranges.id`).
* Range open/close is a soft operation: `PATCH /v1/admin/ranges/{range_id}/status` sets `is_open`; existing check-ins are not force-cleared. The RSO physically ensures the range is vacated during the closing procedure.
* The endpoint is callable from both the **Admin Portal** and the **Kiosk View** RSO dashboard (Level 4+).
* Initial seed: Rifle-Pistol (17 lanes), Skeet-Trap, Air-Rifle, Indoor-Archery, Outdoor-Archery. All seed as closed. `min_training_level` values TBD.
* Lane counts are seeded in the bootstrap migration; future changes use `POST /v1/admin/lanes` and `PATCH /v1/admin/lanes/{lane_id}` without requiring a migration.

### Rejected: PWA / offline-first kiosk

The review recommended implementing the kiosk as a Progressive Web App (PWA) with service workers for offline resilience. This is incompatible with the current design. Stripe Terminal SDK requires direct NFC hardware access, which browser-based service workers cannot reliably provide across all tablet platforms. The kiosk is a **dedicated paired tablet appliance** authenticated by Device Token — this model intentionally avoids browser-based execution for security and reliability reasons.

### Rejected: Django Admin as a substitute for the Admin Portal

The review suggested Django's built-in admin interface as a development advantage. This advantage only applies when no custom admin surface exists. **Outdoor Sports Club** specifies a full-featured **Admin Portal** as a first-class product surface. Django Admin is not a viable substitute for custom role-based UI, range-specific views, and RSO workflows.

### Rejected: Aurora is overkill / switch to standard RDS

The review suggested standard Amazon RDS PostgreSQL as a cost-saving alternative to Aurora. This comparison does not account for the **Aurora Serverless v2** variant in use here. Aurora Serverless v2 scales to 0.5 ACU at idle and targets bursty, weekend-heavy traffic patterns — exactly the usage profile of a physical range facility. Always-on RDS is more expensive for this workload, not less. Aurora Serverless v2 is the correct choice.

### Rejected: DynamoDB as an alternative

The review correctly rejected DynamoDB, consistent with the existing design rationale. Relational integrity is fundamental here — waiver checks, training-level gating, and device pairing all require foreign-key consistency that is complex to enforce in a document store.

### Deferred: Sport-specific metadata (JSONB column)

The review suggested a JSONB column for sport-specific activity metadata (e.g., clays thrown for trap, target distance for archery). This is a reasonable future extension but is premature without a concrete use case. The `activity_logs` schema is sufficient for current scope. Revisit when range-specific analytics are a defined requirement.

### Resolved: Observability strategy (ODQ #14)

The review correctly identified that no centralized monitoring strategy exists. Resolved as **Open Design Question #14** — see decisions below.

**Structured logging:** All Lambda functions emit a single structured JSON log line per request to **Amazon CloudWatch Logs** via `logger.info(json.dumps({...}))`. Required fields: `request_id`, `member_id`, `device_id`, `action`, `duration_ms`, `error`. Check-in handlers additionally log `training_level`; payment handlers additionally log `stripe_payment_intent_id`.

**Distributed tracing:** **AWS X-Ray** is deferred. The traffic volume and latency profile at club scale do not justify the overhead. Re-evaluate if a specific latency problem emerges.

**Alarms:** Three **Amazon CloudWatch Alarms** route to the existing admin **Amazon SNS** SMS topic: (a) Lambda error rate > 1% over 5 minutes, (b) API Gateway 5xx rate > 5%, (c) Aurora ACU > 6.

**Log retention:** All **Amazon CloudWatch Logs** log groups are configured with a 7-year retention period, consistent with the waiver legal retention requirement.

### Accepted: Guest identity uses waiver-on-file lookup

The existing manual process requires guests to sign a new liability form at every visit. The new system replaces this with a waiver-on-file model: a guest's first visit triggers waiver capture at the kiosk (aligned with the ODQ #8 guest-registration flow); on subsequent visits the kiosk looks up the guest by name and phone number and skips re-signing if a valid waiver is already on file.

This requires two new tables: `guests` (persistent identity + waiver metadata, Section 5.8) and `guest_visits` (visit history for annual limit enforcement, Section 5.9). A `guest_id` FK is added to `activity_logs` to link payment and waiver-signing events to specific guests.

The annual visit limit (≤ 2 per guest-member combination per calendar year) is enforced as a hard block — guests that reach the limit are turned away. No RSO override applies to this rule.

### Resolved: Member Portal read endpoints (ODQ #6)

The Member Portal requires two authenticated GET endpoints. Both re-query Aurora on every request — no data is read from JWT claims.

* `GET /v1/members/me` — returns `member_num`, `training_level`, `service_hours`, `dues_paid_until`, `waiver_signed_at`, `mobile_phone`.
* `GET /v1/members/me/badge` — returns `member_num`; the frontend renders this as a QR code for kiosk scanning.

### Resolved: Pairing Code generation (ODQ #7)

The Admin Portal (Level 6 Webmaster) initiates device provisioning via `POST /v1/admin/devices/pairing-code`, which creates a `Pending-Pairing` device row and returns a 15-minute, single-use alphanumeric code. The Webmaster hands the code to the technician configuring the tablet; the tablet calls `POST /v1/devices/pair` to complete pairing and receive its Device Token. No unauthenticated endpoint exposes a code-request surface — all code generation is gated behind Level 6 auth. Pairing code and expiry are stored directly in the `devices` table (`pairing_code`, `pairing_code_expires_at`); both are cleared on successful pairing.

### Resolved: Guest entry point (ODQ #8)

Guests must be physically present with their sponsoring member and check in together at the same kiosk. There is no guest-only entry path. The guest add-on step (after the member's lane is assigned) is the exclusive entry point for guest registration and first-visit waiver capture. This fully covers the ODQ #8 scenario — no separate guest-initiated kiosk flow is needed.

### Resolved: Real-time RSO check-in view (ODQ #9)

Two surfaces serve different audiences:

* **Kiosk lane dashboard** (existing) — shows occupancy for this kiosk's own range only. State is re-fetched after every check-in/check-out transaction and polled every 30 seconds between transactions. No push mechanism required.
* **Admin Portal / mobile web cross-range view** (new) — supervisory read-only view of all ranges and their lane-level occupancy, served by `GET /v1/admin/ranges/occupancy` (Level 4+). Client polls at a suitable interval (e.g., 30 seconds). SSE/WebSockets are not needed at club-scale traffic.

### Resolved: `training_level` promotion (ODQ #4)

All training level changes are explicit **Administrator (Level 5+)** actions. There is no automated promotion rule. An Administrator reviews the member's record and calls `PATCH /v1/admin/members/{member_id}/level` with the new level; the change is recorded in `activity_logs` with `activity_type = 'Level-Change'`. This eliminates the need for an async promotion workflow, **Amazon EventBridge Scheduler**, or **Amazon SQS** for this purpose.

### Deferred: Service hours logging (ODQ #3)

Range-qualified members (Level 3) earn their status by completing a minimum 6-hour volunteer service commitment — RSOs are themselves volunteers. RSO check-in and check-out events recorded in `activity_logs` provide an implicit audit trail of volunteer activity, but automated service-hour calculation and promotion workflows are not a primary function of this system version. The `service_hours` column is retained in `members` as a placeholder for a future integration. Level 1 → Level 2 promotion remains a manual Administrator action (see ODQ #4) until a dedicated service-hours tracking feature is scoped.

### Accepted: Async background workflows are unplanned

The review identified that non-user-facing operations (dues reminders, waiver expiry warnings, service-hours promotion) have no processing layer defined. Captured as **Open Design Question #15**.

## 11. Open Design Questions

The following are unresolved before implementation begins. Each requires a deliberate decision — do not implement with assumed behaviour.

| # | Area | Question |
| :--- | :--- | :--- |
| 1 | **Waiver signing** | What API endpoint handles waiver capture and signature? What is the payload (PDF blob, digital signature string, member acknowledgement)? Which surface captures it — Kiosk only, or also Member Portal on personal devices? |
| 2 | **Dues payment** | How are annual dues paid? **Stripe Terminal** (NFC, kiosk only) or **Stripe.js** (card element, personal device via Member Portal)? A personal-device flow requires a different Stripe integration from the Terminal SDK. |
| 3 | **Service hours logging** | ⏸ Deferred — RSO check-in/check-out events in `activity_logs` serve as an implicit volunteer audit trail. Automated service-hour calculation and promotion are not in scope for this version. `service_hours` retained in `members` as a placeholder. Level 1 → Level 2 promotion remains a manual Administrator action until a dedicated feature is scoped. See Section 10. |
| 4 | **`training_level` promotion** | ✅ Resolved — manual Administrator action only. `PATCH /v1/admin/members/{member_id}/level` (Level 5+); change recorded in `activity_logs`. No automated rule, no async infra required. See Section 7.3 and Section 10. |
| 5 | **Range Open / Close** | ✅ Resolved — see Section 5.2 and Section 7.2. `ranges` table added; `PATCH /v1/admin/ranges/{range_id}/status` sets `is_open` (Level 4+); soft close — RSO physically clears the range. Five ranges seeded: Rifle-Pistol, Skeet-Trap, Air-Rifle, Indoor-Archery, Outdoor-Archery (names provisional). |
| 6 | **Member Portal read endpoints** | ✅ Resolved — `GET /v1/members/me` and `GET /v1/members/me/badge` added to Section 7.1. Both re-query Aurora on every request; no data read from JWT claims. |
| 7 | **Pairing Code generation** | ✅ Resolved — Admin Portal (Level 6) calls `POST /v1/admin/devices/pairing-code` to generate a 15-minute single-use code stored in `devices.pairing_code`. Tablet calls `POST /v1/devices/pair` to complete pairing. No unauthenticated code-request surface. See Section 5.3 and Section 7.3. |
| 8 | **Guest Level 0 flow entry point** | ✅ Resolved — guests must be physically present with their sponsoring member; no independent guest entry path exists. The guest add-on step (after member lane assignment) is the exclusive entry point for first-visit waiver capture and payment. See Section 4 and Section 7.2. |
| 9 | **Real-time RSO check-in view** | ✅ Resolved — kiosk shows local range occupancy (re-fetched after each transaction + 30s poll). Admin Portal / mobile web adds a cross-range supervisory view via `GET /v1/admin/ranges/occupancy` (Level 4+), polled at 30s. No push mechanism required. See Section 7.3 and Section 10. |
| 10 | **Offline operation architecture** | Member check-in and check-out must continue without internet connectivity. Proposed approach: the kiosk caches an encrypted local snapshot of active member QR tokens, `training_level`, and waiver/dues status at regular intervals while online. On connectivity loss, check-in validation runs against the local cache; events are queued and synced when connectivity restores. Guest payment (Stripe Terminal) requires connectivity and cannot be processed offline — policy decision needed: (a) refuse guest entry during outage, or (b) allow RSO to grant provisional entry at their discretion (no payment record until online). The caching strategy, encryption key management, and conflict-resolution on sync must be defined before kiosk implementation begins. |
| 11 | **Violation override flow** | When a check-in fails a rule (guest limit exceeded, waiver expired, etc.), the kiosk enters violation alert state that only a Level 4+ RSO can clear. Two resolution paths are needed: (a) **Approve override** — RSO uses their own credential (PIN, NFC badge, or Admin Portal action) to allow entry anyway and record the exception; (b) **Deny entry** — RSO dismisses the alert, check-in is cancelled, lane remains available. The exact RSO authentication mechanism for clearing the alert (to prevent a user self-clearing) must be defined. |
| 12 | **Lane configuration management** | ✅ Resolved — see Section 5.4 and Section 7.2. Initial counts seeded in bootstrap migration (Rifle-Pistol: 17 lanes); future changes via `POST /v1/admin/lanes` and `PATCH /v1/admin/lanes/{lane_id}` without requiring a migration. |
| 13 | **Kiosk handoff model** | Two physical deployment models are viable: (a) **RSO-mediated** — RSO holds the tablet, hands it to arriving users for check-in, and takes it back on completion. The RSO is physically present at every check-in and can clear violation alerts directly on the device. (b) **Fixed-mount self-serve** — tablet is mounted at the range entrance; users self-scan. Violation alerts must be pushed to the RSO by another mechanism (e.g., audio alert, secondary RSO dashboard). The handoff model affects the violation-clearing UX, the physical mounting requirements, and whether the tablet needs a "return to RSO dashboard" post-check-in state. |
| 14 | **Observability strategy** | ✅ Resolved — see Section 10. Structured JSON logging to **Amazon CloudWatch Logs**; X-Ray deferred; three alarms to admin **Amazon SNS** topic; 7-year log retention. |
| 15 | **Async background workflow scope** | Several non-user-facing operations are currently unplanned: annual dues renewal reminders, waiver expiry warnings (e.g., 30-day advance SMS via **Amazon SNS**), service-hours promotion evaluation (`service_hours >= 6` → Level 2), and audit log export to **Amazon S3** for admin review. These are candidates for an async processing layer (**Amazon SQS** + **AWS Lambda** worker or **Amazon EventBridge Scheduler**). Decisions needed: (a) which events trigger which notifications; (b) whether promotion to Level 2 is fully automated or requires admin confirmation; (c) what the retry and dead-letter policy is for failed notification deliveries. |
| 16 | **Guest lookup key** | ✅ Resolved — `guests` uses `(first_name, last_name, phone, email)` as the composite lookup key and unique constraint (Section 5.8). Email is collected alongside name and phone during the kiosk guest add-on step. |
