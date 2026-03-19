---
description: "Use when writing, editing, or reviewing database migrations, schema definitions, or RLS policies. Covers Amazon Aurora Serverless v2 (PostgreSQL) conventions, migration patterns, Row-Level Security, indexing, and AWS Backup configuration for the Outdoor Sports Club project."
applyTo: "db/**/*.sql"
---

# Database Standards — Outdoor Sports Club

## AWS Services in Use

| Service | Purpose |
| :--- | :--- |
| **Amazon Aurora Serverless v2** | PostgreSQL-compatible managed database; scales to zero when idle |
| **RDS Data API** | Sole access method from Lambda — no persistent connections |
| **AWS KMS** | Encryption at rest for Aurora storage and automated backups |
| **AWS Backup** | PITR (35-day window) + cross-region snapshot replication to `us-west-2` |
| **AWS Secrets Manager** | Stores Aurora master credentials; referenced by RDS Data API |

## Migration File Conventions

* Migration files live in `db/migrations/` and are named `<zero-padded-sequence>_<snake_case_description>.sql`
    * e.g., `0001_create_members.sql`, `0012_add_consumable_purchases.sql`
* Every migration file must begin with a version comment and be idempotent:

```sql
-- Migration: 0012_add_consumable_purchases
-- Description: Creates the consumable_purchases table for kiosk sales tracking.

CREATE TABLE IF NOT EXISTS consumable_purchases (
    ...
);
```

* Use `IF NOT EXISTS` for `CREATE TABLE` and `CREATE INDEX`
* Use `IF NOT EXISTS` column guard for `ADD COLUMN`:

```sql
ALTER TABLE members ADD COLUMN IF NOT EXISTS new_column TEXT;
```

* Never use `DROP TABLE`, `DROP COLUMN`, or `TRUNCATE` in a forward migration — use a separate `rollback/` script if a destructive operation is ever needed
* All migrations must be reviewed against `docs/design.md` Section 5 before merging

## Naming Conventions

* Table names: `snake_case`, plural (e.g., `members`, `activity_logs`, `consumable_purchases`)
* Column names: `snake_case`
* Primary keys: always named `id`
* Foreign keys: `<referenced_table_singular>_id` (e.g., `member_id`, `device_id`)
* Indexes: `idx_<table>_<column(s)>` (e.g., `idx_activity_logs_member_id`)
* RLS policies: `policy_<table>_<role>` (e.g., `policy_members_self`, `policy_members_admin`)

## Data Types

| Use case | Type |
| :--- | :--- |
| Entity primary key | `UUID DEFAULT gen_random_uuid()` |
| High-volume append-only log PK | `BIGINT GENERATED ALWAYS AS IDENTITY` |
| Training level | `SMALLINT NOT NULL CHECK (training_level BETWEEN 0 AND 6)` |
| Monetary amounts | `DECIMAL(8,2) NOT NULL` |
| Timestamps | `TIMESTAMPTZ NOT NULL DEFAULT now()` |
| Status enumerations | `TEXT NOT NULL CHECK (status IN (...))` — avoid `ENUM` type for Aurora compatibility |
| Nullable foreign keys | `UUID REFERENCES <table>(id) ON DELETE SET NULL` |

## Row-Level Security (RLS)

### Tables requiring RLS

Enable RLS on every table that contains member PII or links records to a specific member:

| Table | Reason |
| :--- | :--- |
| `members` | Core identity and PII |
| `activity_logs` | Links check-in/out events to a specific member |
| `consumable_purchases` | Links purchases to a specific member (nullable — see below) |
| `guest_visits` | Links visits to the sponsoring member |
| `guests` | Contains PII: `first_name`, `last_name`, `phone`, `email` |

### Tables intentionally excluded from RLS

These tables contain no member PII. Access is enforced exclusively at the API layer (Lambda + API Gateway). Do not add RLS to these tables unless the threat model changes.

| Table | Reason excluded |
| :--- | :--- |
| `lanes` | Operational state only; `current_member_id` FK is not PII |
| `wait_list` | Operational state only; `member_id` FK is not PII |
| `devices` | Hardware identity; no member PII |
| `ranges` | Reference data; read-only for all authenticated callers |
| `training_level_policies` | Reference data; no member PII |
| `club_settings` | Singleton config; no member PII; admin-write only |

### `current_setting` — always use `missing_ok = true`

All RLS policy expressions must use `current_setting('app.current_member_id', true)` (two-argument form). The second argument `true` is the `missing_ok` flag.

**Why this matters:** Without `missing_ok`, PostgreSQL raises a hard error if the session variable is not set. This will crash any query against the table during manual debug sessions, migrations run outside Lambda context, and any code path that forgets to set the variable. With `missing_ok = true`, an unset variable returns `NULL` — and `NULL` in a `USING` or `WITH CHECK` expression evaluates to `false`, so the policy is **fail-closed**: no rows are accessible.

```sql
-- WRONG — raises error if session variable is absent
CREATE POLICY policy_members_self ON members
    FOR SELECT
    USING (id = current_setting('app.current_member_id')::uuid);

-- CORRECT — fail-closed when session variable is absent
CREATE POLICY policy_members_self ON members
    FOR SELECT
    USING (id = current_setting('app.current_member_id', true)::uuid);
```

### Standard policy pattern

```sql
-- Members can only SELECT their own row
CREATE POLICY policy_members_self ON members
    FOR SELECT
    USING (id = current_setting('app.current_member_id', true)::uuid);

-- Level 4+ can SELECT all rows (set via RDS Data API session variable)
CREATE POLICY policy_members_admin ON members
    FOR ALL
    USING (current_setting('app.current_training_level', true)::int >= 4);
```

`activity_logs` and `guest_visits` follow the same pattern using the `member_id` column.

### Nullable FK columns in INSERT policies

If the `member_id` column on a table is **nullable** (e.g., `consumable_purchases.member_id` is null for guest purchases), a naive `WITH CHECK (member_id = current_setting(...))` will **reject all NULL inserts**. Use this pattern instead:

```sql
-- consumable_purchases.member_id is nullable (guest purchases have member_id = NULL).
-- Allow insert when the session is authenticated AND either:
--   (a) the row is a guest purchase (member_id IS NULL), or
--   (b) the member_id matches the current session.
CREATE POLICY policy_consumable_purchases_kiosk_insert ON consumable_purchases
    FOR INSERT
    WITH CHECK (
        current_setting('app.current_member_id', true) IS NOT NULL
        AND (
            member_id IS NULL
            OR member_id = current_setting('app.current_member_id', true)::uuid
        )
    );
```

**Rule:** Before writing any INSERT or UPDATE policy, check whether the target FK column is nullable in the table definition. If it is, the `WITH CHECK` expression must explicitly handle the `NULL` case.

### Enabling RLS

```sql
ALTER TABLE members ENABLE ROW LEVEL SECURITY;
ALTER TABLE members FORCE ROW LEVEL SECURITY;
```

`ALTER TABLE ... ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` are idempotent and safe to re-run. Use `DROP POLICY IF EXISTS` before `CREATE POLICY` to keep migration files idempotent.

* The Lambda handler sets `app.current_member_id` and `app.current_training_level` as session variables via the RDS Data API before executing any query
* Tables that contain no member PII do not require RLS but must still enforce access via API-layer auth

## Indexes

Always create indexes on:

* **All foreign key columns** — Aurora does not auto-index FKs; every FK column must have a `CREATE INDEX IF NOT EXISTS` entry, without exception
* `activity_logs.timestamp` (range queries for reporting)
* `activity_logs.activity_type` (filter by event type)
* `members.email` and `members.member_num` (lookup columns)
* `devices.device_token` (kiosk auth lookup — every request)

```sql
CREATE INDEX IF NOT EXISTS idx_activity_logs_member_id ON activity_logs (member_id);
CREATE INDEX IF NOT EXISTS idx_activity_logs_timestamp  ON activity_logs (timestamp);
CREATE INDEX IF NOT EXISTS idx_devices_device_token     ON devices (device_token);
```

**FK index audit:** After writing a `CREATE TABLE` statement, scan every column definition for `REFERENCES` and verify a corresponding `CREATE INDEX IF NOT EXISTS` exists for that column before committing. Missing FK indexes are a common review finding.

## Backup & Recovery

* PITR is enabled at the Aurora cluster level (35-day window) — no per-migration action required
* **AWS Backup** plan replicates daily snapshots to `us-west-2`
* To restore: the **Webmaster (Level 6)** initiates PITR via the AWS Console or CLI, specifying the target second; restoration creates a new cluster — DNS must be updated to cut over
* Never disable PITR or modify the backup retention window without **Webmaster** approval

## Security Reminders

* No PII in migration comments or seed data files
* Never commit real member data to the repository — use anonymised fixtures for development
* `device_token` values must be stored as a salted hash — never plaintext
* `social_provider_id` is nullable and is cleared during the Recovery Protocol — ensure `ON DELETE SET NULL` is not needed (the member row is not deleted; only this column is cleared)
