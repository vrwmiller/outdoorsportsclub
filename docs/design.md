# design.md

## 1. Training-Centric Access Schema (RBAC)

The system's **Role-Based Access Control (RBAC)** is driven by the user's verified "Training Level." This serves as a digital gatekeeper at the **Member Portal**, the **Admin Portal**, and the **Mobile Kiosks**.

The application has four surfaces. The **Home Page** is the club's primary public-facing interface and the entry point for all website visitors. After login, users are routed to the **Member Portal** (Level 0–3) or the **Admin Portal** (Level 4–6). The **Kiosk View** is the default full-screen interface served to paired range tablets and is accessed exclusively via Device Token — it is entirely separate from the website login flow.

| Level | Designation | Digital Permissions | Range & System Logic |
| :--- | :--- | :--- | :--- |
| **0** | **Guest** | Waiver & Payment | Must pay guest fee and sign digital form at Kiosk. |
| **1** | **Probationary** | Service Tracker | Restricted range access; focus on logging 6 required service hours. |
| **2** | **Basic Member** | General Access | Unlocks check-in for basic facilities (Skeet, Trap, Archery). |
| **3** | **Qualified** | Specialized Access | Verified Qualification unlocks specialized Rifle/Pistol ranges. |
| **4** | **RSO / Instructor**| Range Ops | Can "Open/Close" ranges and override guest limits. |
| **5** | **Administrator** | Business Oversight | **Full Business Access:** Finance, Database, and Rules. |
| **6** | **Webmaster** | **Technical Oversight** | **Full System Access:** API logs, Device Pairing, and Recovery. |

## 2. Kiosk Identity & Device Provisioning (AWS)

To ensure high-speed check-ins and eliminate the security risks of social login on shared tablets, the system utilizes **Secure Device Pairing**:

* **Pairing Workflow:** New tablets generate a short-lived **Pairing Code**. A **Webmaster (Level 6)** authorizes the code via the Admin Portal to link the hardware.
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

* **The "Safety Gate":** Automated blocking of check-ins for members with insufficient `training_level` for a specific range.
* **Mandatory Check-Out:** Range users are required to check out when leaving a range. Check-out is logged as a `Range-Checkout` event via the same kiosk QR scan flow used for check-in.
* **Cashless Guest Fees:** Integrated "Tap-to-Pay" (NFC) via mobile tablets at the range, powered by the **Stripe Terminal SDK**. No additional card reader hardware is required — the tablet's built-in NFC chip acts as the payment terminal.
* **Consumable Sales:** Members and guests may purchase consumables (e.g., targets, canned soda, coffee) at the kiosk. Each transaction is recorded in the `consumable_purchases` table with full line-item detail. Payment is processed via **Stripe Terminal SDK** (Tap to Pay). **Known Limitation:** There is no reliable physical process to verify that recorded quantities match items actually dispensed; the system records what is entered at the kiosk but cannot enforce inventory accuracy.
* **Time-Bound Waivers:** Automated re-signing triggers for Safety Waivers based on 1-year expiration logic.
* **Tablet Hardware Requirement:** Kiosk tablets **must have an accessible NFC chip** to support Tap to Pay. Most modern Android tablets and iPads qualify. Budget or older Android tablets may omit NFC — verify hardware specs before purchasing.

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

### **5.2 Table: `devices` (Kiosks)**

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | UUID (PK) | Unique hardware ID. |
| `device_token` | TEXT | Salted hash of the secret used for **Kiosk-to-API** authentication. |
| `location_tag` | TEXT | Human-readable name (e.g., "Skeet-Field-1"). |
| `min_training_level` | SMALLINT (0-6) | Minimum `training_level` required to check in at this kiosk's range. |
| `status` | TEXT | `Pending-Pairing`, `Active`, `Revoked` |

### **5.3 Table: `activity_logs`**

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | BIGINT (PK) | High-volume log ID. |
| `member_id` | UUID (FK) | Reference to the `members` table. |
| `device_id` | UUID (FK) | Reference to the `devices` table. |
| `activity_type` | TEXT | `Range-Checkin`, `Range-Checkout`, `Guest-Payment`, `Waiver-Signed` |
| `stripe_payment_intent_id` | TEXT (Nullable) | Stripe Payment Intent ID; populated for `Guest-Payment` events only. |
| `timestamp` | TIMESTAMP | Audit-ready event time. |

### **5.4 Table: `consumable_purchases`**

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

## 6. Infrastructure & Security (AWS)

* **Storage:** Signed waivers are stored in **Amazon S3** with **S3 Object Lock** (Compliance Mode) to prevent tampering or accidental deletion.
* **Notifications:** Urgent safety alerts or range closures are pushed via **Amazon SNS** (SMS) to ensure reach to 100% of members.
* **Zero-Trust Security:** Data is encrypted at rest and in transit via **AWS KMS**; no raw credit card data is ever stored on Club-managed systems.

## 7. API Outlines (AWS-Native / RESTful)

The API layer is built using **AWS Lambda** and **Amazon API Gateway**, integrated via **AWS Amplify**.

### **7.1 Kiosk Operations**

* **`POST /v1/kiosk/check-in`**
  * **Logic:** Triggered by a QR scan. Validates `training_level` and `waiver_status` via the **RDS Data API**.
  * **Returns:** `200 OK` (Access Granted) or `403 Forbidden` (e.g., "Level 3 Required").

* **`POST /v1/kiosk/check-out`**
  * **Logic:** Triggered by a QR scan at range exit. Validates an active open `Range-Checkin` exists for the member on that device; writes a `Range-Checkout` record to `activity_logs`.
  * **Returns:** `200 OK` (Check-Out Logged) or `404 Not Found` (no open check-in on record).

* **`POST /v1/kiosk/guest-payment`**
  * **Logic:** Orchestrates guest fee payment via the **Stripe Terminal SDK** (Tap to Pay on tablet NFC); creates `activity_logs` entry upon success.

* **`POST /v1/kiosk/consumable-purchase`**
  * **Logic:** Records one or more line items (item name, quantity, unit price) to `consumable_purchases`; processes payment via **Stripe Terminal SDK** (Tap to Pay). `member_id` is optional — omit for anonymous guest purchases.
  * **Returns:** `200 OK` (Purchase Recorded) or `402 Payment Required` (Stripe payment failure).

### **7.2 Administrative & Recovery**

* **`PATCH /v1/admin/members/reset-auth`** (**Level 6** **Webmaster** Only)
  * **Logic:** Clears the `social_provider_id` in the **Cognito User Pool** for the specific `member_id`.

* **`POST /v1/devices/pair`** (**Level 6** **Webmaster** Only)
  * **Logic:** Validates the tablet's **Pairing Code**; promotes device to 'Active' and returns the `device_token`.

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
| Development / staging | 1 (primary only) | `RegionList: us-east-1` |
| Production launch | 1 (primary) | `RegionList: us-east-1` |
| Multi-region active-active | 2+ | `RegionList: us-east-1,us-west-2` |

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

### Backup & point-in-time recovery

* **Aurora PITR:** 35-day continuous backup window; restore to any second
* **AWS Backup:** Daily snapshot at 02:00 UTC; 35-day retention; cross-region copy to every region in `RegionList`
* **AWS Backup Vault Lock:** Compliance mode on `prod` vaults only — snapshots cannot be deleted before retention expires; Vault Lock is **not** enabled on `dev`

### The "Red Button" procedure

In a full primary-region failure with active-active enabled: **Aurora Global Database** fails over and promotes a reader cluster in a secondary region to writer, and **Route 53** updates DNS to route traffic to the healthy regional endpoint. In single-region mode: the **Webmaster** deploys the stack to a new region using the IaC parameters and restores Aurora from **AWS Backup** or an Aurora point-in-time restore/snapshot. Target RTO: under 60 minutes from a cold start.

## 9. Open Design Questions

The following are unresolved before implementation begins. Each requires a deliberate decision — do not implement with assumed behaviour.

| # | Area | Question |
| :--- | :--- | :--- |
| 1 | **Waiver signing** | What API endpoint handles waiver capture and signature? What is the payload (PDF blob, digital signature string, member acknowledgement)? Which surface captures it — Kiosk only, or also Member Portal on personal devices? |
| 2 | **Dues payment** | How are annual dues paid? **Stripe Terminal** (NFC, kiosk only) or **Stripe.js** (card element, personal device via Member Portal)? A personal-device flow requires a different Stripe integration from the Terminal SDK. |
| 3 | **Service hours logging** | What is the endpoint and flow for recording service hours? Who initiates the log entry — the member self-reporting, an RSO verifying on-site, or an **Administrator**? What prevents false entries? |
| 4 | **`training_level` promotion** | What triggers a level change — a manual **Administrator** action, an automated rule (e.g., `service_hours >= 6` auto-promotes Level 1 → Level 2), or both? What is the API endpoint? |
| 5 | **Range Open / Close** | How is a range marked open or closed? Is there a `ranges` table with an `is_open` flag? What is the API endpoint and who calls it (Level 4+)? The check-in flow must refuse entry to a closed range — the schema and endpoint need to be defined before check-in can be implemented. |
| 6 | **Member Portal read endpoints** | No GET endpoints are defined. The Member Portal needs to fetch member profile, `training_level`, `service_hours`, `dues_paid_until`, `waiver_signed_at`, and the QR badge token. These endpoints need to be added to Section 7. |
| 7 | **Pairing Code generation** | `POST /v1/devices/pair` accepts a Pairing Code, but there is no defined flow for how a new tablet *generates* the code. Is this a one-time code displayed in the Admin Portal that the tablet manually enters, or does the tablet call an unauthenticated endpoint to request a code? |
| 8 | **Guest Level 0 flow entry point** | Guests must pay a fee and sign a waiver at the kiosk. Does the kiosk allow starting this flow without scanning a QR code? The current check-in endpoint assumes a QR scan. A separate guest-registration flow — or a kiosk-initiated guest session — may be needed. |

