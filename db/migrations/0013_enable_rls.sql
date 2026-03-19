-- Migration: 0013_enable_rls
-- Description: Enables Row-Level Security on all member-data and PII tables and defines
--              access policies. Lambda handlers must set app.current_member_id and
--              app.current_training_level as session variables via the RDS Data API before
--              executing any query on these tables.
--
--              current_setting(..., true) uses the missing_ok flag so that an unset session
--              variable returns NULL instead of raising an error. NULL propagation means no
--              rows are accessible (fail-closed) when session variables are absent.
--
--              Tables intentionally excluded from RLS:
--                lanes     — operational state only; no PII; access enforced at API layer.
--                wait_list — operational state only; no PII; access enforced at API layer.
--                devices   — no member PII; access enforced at API layer.
--                ranges    — reference data; no member PII; read-only for all authed callers.
--                training_level_policies — reference data; no member PII.
--                club_settings           — singleton; no member PII; admin-write only.
--
--              ALTER TABLE ... ENABLE/FORCE ROW LEVEL SECURITY is idempotent.
--              Policies use DROP IF EXISTS + CREATE to remain idempotent on re-run.

-- ---------------------------------------------------------------------------
-- members
-- ---------------------------------------------------------------------------
ALTER TABLE members ENABLE ROW LEVEL SECURITY;
ALTER TABLE members FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS policy_members_self  ON members;
DROP POLICY IF EXISTS policy_members_admin ON members;

-- Members may SELECT only their own row.
CREATE POLICY policy_members_self ON members
    FOR SELECT
    USING (id = current_setting('app.current_member_id', true)::uuid);

-- Level 4+ may perform all operations on all rows.
CREATE POLICY policy_members_admin ON members
    FOR ALL
    USING (current_setting('app.current_training_level', true)::int >= 4);

-- ---------------------------------------------------------------------------
-- activity_logs
-- ---------------------------------------------------------------------------
ALTER TABLE activity_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE activity_logs FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS policy_activity_logs_self          ON activity_logs;
DROP POLICY IF EXISTS policy_activity_logs_kiosk_insert  ON activity_logs;
DROP POLICY IF EXISTS policy_activity_logs_admin         ON activity_logs;

CREATE POLICY policy_activity_logs_self ON activity_logs
    FOR SELECT
    USING (member_id = current_setting('app.current_member_id', true)::uuid);

CREATE POLICY policy_activity_logs_kiosk_insert ON activity_logs
    FOR INSERT
    WITH CHECK (member_id = current_setting('app.current_member_id', true)::uuid);

CREATE POLICY policy_activity_logs_admin ON activity_logs
    FOR ALL
    USING (current_setting('app.current_training_level', true)::int >= 4);

-- ---------------------------------------------------------------------------
-- consumable_purchases
-- ---------------------------------------------------------------------------
ALTER TABLE consumable_purchases ENABLE ROW LEVEL SECURITY;
ALTER TABLE consumable_purchases FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS policy_consumable_purchases_self          ON consumable_purchases;
DROP POLICY IF EXISTS policy_consumable_purchases_kiosk_insert  ON consumable_purchases;
DROP POLICY IF EXISTS policy_consumable_purchases_admin         ON consumable_purchases;

CREATE POLICY policy_consumable_purchases_self ON consumable_purchases
    FOR SELECT
    USING (member_id = current_setting('app.current_member_id', true)::uuid);

-- member_id is nullable (guest purchases have member_id = NULL).
-- Allow insert when the session is authenticated AND either the row is a guest
-- purchase (member_id IS NULL) or the member_id matches the current session.
CREATE POLICY policy_consumable_purchases_kiosk_insert ON consumable_purchases
    FOR INSERT
    WITH CHECK (
        current_setting('app.current_member_id', true) IS NOT NULL
        AND (
            member_id IS NULL
            OR member_id = current_setting('app.current_member_id', true)::uuid
        )
    );

CREATE POLICY policy_consumable_purchases_admin ON consumable_purchases
    FOR ALL
    USING (current_setting('app.current_training_level', true)::int >= 4);

-- ---------------------------------------------------------------------------
-- guest_visits
-- ---------------------------------------------------------------------------
ALTER TABLE guest_visits ENABLE ROW LEVEL SECURITY;
ALTER TABLE guest_visits FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS policy_guest_visits_self          ON guest_visits;
DROP POLICY IF EXISTS policy_guest_visits_kiosk_insert  ON guest_visits;
DROP POLICY IF EXISTS policy_guest_visits_admin         ON guest_visits;

CREATE POLICY policy_guest_visits_self ON guest_visits
    FOR SELECT
    USING (member_id = current_setting('app.current_member_id', true)::uuid);

CREATE POLICY policy_guest_visits_kiosk_insert ON guest_visits
    FOR INSERT
    WITH CHECK (member_id = current_setting('app.current_member_id', true)::uuid);

CREATE POLICY policy_guest_visits_admin ON guest_visits
    FOR ALL
    USING (current_setting('app.current_training_level', true)::int >= 4);

-- ---------------------------------------------------------------------------
-- guests (PII: first_name, last_name, phone, email)
-- Any authenticated kiosk session (current_member_id set) may SELECT and INSERT
-- guest records — the sponsoring member context is always present during check-in.
-- Level 4+ may perform all operations.
-- ---------------------------------------------------------------------------
ALTER TABLE guests ENABLE ROW LEVEL SECURITY;
ALTER TABLE guests FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS policy_guests_member_lookup ON guests;
DROP POLICY IF EXISTS policy_guests_member_insert ON guests;
DROP POLICY IF EXISTS policy_guests_admin         ON guests;

-- Any authenticated member session may look up guest records during the guest add-on flow.
CREATE POLICY policy_guests_member_lookup ON guests
    FOR SELECT
    USING (current_setting('app.current_member_id', true) IS NOT NULL);

-- Any authenticated member session may insert a new guest record.
CREATE POLICY policy_guests_member_insert ON guests
    FOR INSERT
    WITH CHECK (current_setting('app.current_member_id', true) IS NOT NULL);

-- Level 4+ may perform all operations (including UPDATE for waiver refresh).
CREATE POLICY policy_guests_admin ON guests
    FOR ALL
    USING (current_setting('app.current_training_level', true)::int >= 4);
