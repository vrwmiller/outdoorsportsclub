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
| **4** | **RSO / Instructor** | Range Ops | Can "Open/Close" ranges and override guest limits. |
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

### Physical kiosk model

Staffed ranges (Rifle/Pistol, Skeet/Trap, and staffed Archery and Air Rifle) each have 2–3 tablet kiosks. Unstaffed ranges (outdoor Archery and indoor Air Rifle when not staffed) do not have kiosks — no check-in flow applies.

The kiosk handoff model — whether the RSO holds the tablet and hands it to arriving users, or the tablet is fixed-mount and self-serve — is an **open design question (#13)**. Both models are supportable by the same underlying check-in flow; the difference is physical deployment and the violation-clearing mechanism.

### Kiosk states

| State | Description |
| :--- | :--- |
| **RSO Dashboard** | Default view. Displays lane occupancy for this kiosk's range: each lane shows `Available` or the name/member number of the assigned occupant and their guest count. |
| **Check-in flow** | Initiated by RSO. Member scans QR Badge; system validates `training_level`, waiver, dues, and guest count. |
| **Guest add-on** | After the member's lane is assigned, the kiosk prompts: "Add guests? (0 / 1 / 2)." For each guest, the kiosk collects a waiver acknowledgement and presents a payment screen — either the guest or the sponsoring member may tap to pay. Guests share the member's lane. |
| **Violation alert** | Displayed when check-in fails a rule (e.g., guest limit exceeded, waiver expired, insufficient level). The user cannot dismiss this screen — only the RSO can clear it by either resolving the issue or denying entry. |
| **Lane assignment** | After check-in (and optional guest add-on) is complete, the assigned lane and guest count are confirmed on screen. |
| **Check-out flow** | RSO-initiated or user-initiated. Member scans QR Badge; open lane assignment (including all guests on that lane) is closed and the lane returns to `Available`. |

### Flow rules

* **The "Safety Gate":** Automated blocking of check-ins for members with insufficient `training_level` for a specific range.
* **Mandatory Check-Out:** Range users must check out before leaving. Check-out closes the lane assignment (including all guests) and logs a `Range-Checkout` event.
* **Violation lock:** A failed check-in locks the screen in violation state. The RSO resolves — approve an override where policy allows, or deny entry. Only Level 4+ can clear a violation alert.
* **Lane assignment:** Each member check-in assigns one available lane. Member and all their guests share that lane. If no lanes are available, check-in is blocked.
* **Guest sponsorship:** Guests must be accompanied by a sponsoring member. A member may bring a maximum of **2 guests per range visit**. The limit is enforced per range — a member may not bring more than 2 guests on the same range at the same time. Guest count is stored in `lanes.guest_count` and checked at check-in.
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

### **5.2 Table: `devices` (Kiosks)**

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | UUID (PK) | Unique hardware ID. |
| `device_token` | TEXT | Salted hash of the secret used for **Kiosk-to-API** authentication. |
| `location_tag` | TEXT | Human-readable name (e.g., "Skeet-Field-1"). |
| `min_training_level` | SMALLINT (0-6) | Minimum `training_level` required to check in at this kiosk's range. |
| `status` | TEXT | `Pending-Pairing`, `Active`, `Revoked` |

### **5.3 Table: `lanes`**

Each lane belongs to a range and tracks current occupancy. The `devices` table links kiosks to ranges; lanes belong to ranges, not to individual kiosk tablets.

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | UUID (PK) | Unique lane identifier. |
| `range_tag` | TEXT | Range-level identifier (e.g., `Rifle-Range`, `Skeet-Field`). This is the range prefix; `devices.location_tag` extends it with a kiosk instance suffix (e.g., `Skeet-Field-1`). Once the `ranges` table (ODQ #5) is introduced, this column should become a `range_id` FK. |
| `lane_number` | SMALLINT | Lane number within the range (e.g., 1–10). |
| `status` | TEXT | `Available`, `Occupied` |
| `guest_count` | SMALLINT | Number of guests currently sharing this lane with the sponsoring member (0–2). Always 0 when `status` is `Available`. |
| `current_member_id` | UUID (FK, Nullable) | FK to `members.id`; set on check-in, cleared on check-out. Nullable only when the lane is `Available`. Guests must be accompanied by a member — the lane is assigned to the sponsoring member's ID for the duration of the guest's occupancy. A null value always means the lane is unoccupied. |
| `checked_in_at` | TIMESTAMP (Nullable) | Time the lane was last claimed. |

**Constraints and indexes:**

* `UNIQUE (range_tag, lane_number)` — no two lanes can share the same number within a range.
* `CHECK (status IN ('Available', 'Occupied'))`
* `CHECK (guest_count BETWEEN 0 AND 2)`
* `CHECK (status = 'Available' AND current_member_id IS NULL AND guest_count = 0 OR status = 'Occupied' AND current_member_id IS NOT NULL AND guest_count BETWEEN 0 AND 2)` — enforces consistency between occupancy state, sponsoring member, and guest count.
* `INDEX ON (range_tag, status)` — supports finding available/occupied lanes for a range.
* `INDEX ON (current_member_id)` — supports finding the lane a member is currently occupying.

### **5.4 Table: `activity_logs`**

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | BIGINT (PK) | High-volume log ID. |
| `member_id` | UUID (FK) | Reference to the `members` table. |
| `device_id` | UUID (FK) | Reference to the `devices` table. |
| `activity_type` | TEXT | `Range-Checkin`, `Range-Checkout`, `Guest-Payment`, `Waiver-Signed` |
| `lane_id` | UUID (FK, Nullable) | Lane associated with the activity. Populated for `Range-Checkin`, `Range-Checkout`, and `Guest-Payment` events so that payments can be tied to a specific range visit and lane for reconciliation and dispute resolution; null only for `Waiver-Signed` events with no lane context. |
| `stripe_payment_intent_id` | TEXT (Nullable) | Stripe Payment Intent ID; populated for `Guest-Payment` events only and linked to the lane/visit via `lane_id`. |
| `timestamp` | TIMESTAMP | Audit-ready event time. |

### **5.5 Table: `consumable_purchases`**

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
* **Authorization invariant — `training_level`:** Every Lambda that gates access by training level **must re-query `training_level` from Aurora** on every request. It must never be read from the Cognito JWT claim. The JWT is used only to identify the caller (via `sub`); the authoritative level is always the database row. A member's level can be revoked between token issuance and token expiry — reading the claim would miss that change.

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

### Accepted: Real-time RSO check-in view is a gap

The review correctly identified that RSOs have no current mechanism to see who is checked in on their range in real time. This is captured as **Open Design Question #9**. Polling a `GET /v1/ranges/{id}/checkins` endpoint is the recommended starting point before considering SSE or WebSockets.

### Accepted: A `ranges` table is needed

The review independently confirmed the need for a `ranges` or "range segments" entity (e.g., Trap House 1, Pistol Bay A) to support range-specific check-in validation and status. This is already captured as **Open Design Question #5** and is a prerequisite for implementing check-in logic.

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

### Accepted: Async background workflows are unplanned

The review identified that non-user-facing operations (dues reminders, waiver expiry warnings, service-hours promotion) have no processing layer defined. Captured as **Open Design Question #15**.

## 11. Open Design Questions

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
| 9 | **Real-time RSO check-in view** | The primary RSO view is the **kiosk lane dashboard** (Section 4), which shows live lane occupancy on the tablet itself. A secondary read-only view in the **Admin Portal** may also be needed for supervisory oversight across all ranges. The kiosk dashboard requires the same real-time data as check-in/check-out, so no additional push mechanism is needed if the kiosk re-fetches lane state after each transaction. A background polling interval (e.g., every 30s) is sufficient for the kiosk dashboard between transactions. |
| 10 | **Offline operation architecture** | Member check-in and check-out must continue without internet connectivity. Proposed approach: the kiosk caches an encrypted local snapshot of active member QR tokens, `training_level`, and waiver/dues status at regular intervals while online. On connectivity loss, check-in validation runs against the local cache; events are queued and synced when connectivity restores. Guest payment (Stripe Terminal) requires connectivity and cannot be processed offline — policy decision needed: (a) refuse guest entry during outage, or (b) allow RSO to grant provisional entry at their discretion (no payment record until online). The caching strategy, encryption key management, and conflict-resolution on sync must be defined before kiosk implementation begins. |
| 11 | **Violation override flow** | When a check-in fails a rule (guest limit exceeded, waiver expired, etc.), the kiosk enters violation alert state that only a Level 4+ RSO can clear. Two resolution paths are needed: (a) **Approve override** — RSO uses their own credential (PIN, NFC badge, or Admin Portal action) to allow entry anyway and record the exception; (b) **Deny entry** — RSO dismisses the alert, check-in is cancelled, lane remains available. The exact RSO authentication mechanism for clearing the alert (to prevent a user self-clearing) must be defined. |
| 12 | **Lane configuration management** | Lane count per range is needed by the `lanes` table. How are lanes created and managed — static seed data in a DB migration, or configurable via the **Admin Portal**? If lane counts change (range expansion, temporary closure of lanes), the Admin Portal must support adding/removing/disabling lanes without a migration. |
| 13 | **Kiosk handoff model** | Two physical deployment models are viable: (a) **RSO-mediated** — RSO holds the tablet, hands it to arriving users for check-in, and takes it back on completion. The RSO is physically present at every check-in and can clear violation alerts directly on the device. (b) **Fixed-mount self-serve** — tablet is mounted at the range entrance; users self-scan. Violation alerts must be pushed to the RSO by another mechanism (e.g., audio alert, secondary RSO dashboard). The handoff model affects the violation-clearing UX, the physical mounting requirements, and whether the tablet needs a "return to RSO dashboard" post-check-in state. |
| 14 | **Observability strategy** | ✅ Resolved — see Section 10. Structured JSON logging to **Amazon CloudWatch Logs**; X-Ray deferred; three alarms to admin **Amazon SNS** topic; 7-year log retention. |
| 15 | **Async background workflow scope** | Several non-user-facing operations are currently unplanned: annual dues renewal reminders, waiver expiry warnings (e.g., 30-day advance SMS via **Amazon SNS**), service-hours promotion evaluation (`service_hours >= 6` → Level 2), and audit log export to **Amazon S3** for admin review. These are candidates for an async processing layer (**Amazon SQS** + **AWS Lambda** worker or **Amazon EventBridge Scheduler**). Decisions needed: (a) which events trigger which notifications; (b) whether promotion to Level 2 is fully automated or requires admin confirmation; (c) what the retry and dead-letter policy is for failed notification deliveries. |
