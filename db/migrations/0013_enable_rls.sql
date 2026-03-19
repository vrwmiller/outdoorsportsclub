-- Migration: 0013_enable_rls
-- Description: Enables Row-Level Security on all member-data tables and defines access policies.
--              Lambda handlers must set app.current_member_id and app.current_training_level as
--              session variables via the RDS Data API before executing any query on these tables.
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
    USING (id = current_setting('app.current_member_id')::uuid);

-- Level 4+ may perform all operations on all rows.
CREATE POLICY policy_members_admin ON members
    FOR ALL
    USING (current_setting('app.current_training_level')::int >= 4);

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
    USING (member_id = current_setting('app.current_member_id')::uuid);

CREATE POLICY policy_activity_logs_kiosk_insert ON activity_logs
    FOR INSERT
    WITH CHECK (member_id = current_setting('app.current_member_id')::uuid);

CREATE POLICY policy_activity_logs_admin ON activity_logs
    FOR ALL
    USING (current_setting('app.current_training_level')::int >= 4);

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
    USING (member_id = current_setting('app.current_member_id')::uuid);

CREATE POLICY policy_consumable_purchases_kiosk_insert ON consumable_purchases
    FOR INSERT
    WITH CHECK (member_id = current_setting('app.current_member_id')::uuid);

CREATE POLICY policy_consumable_purchases_admin ON consumable_purchases
    FOR ALL
    USING (current_setting('app.current_training_level')::int >= 4);

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
    USING (member_id = current_setting('app.current_member_id')::uuid);

CREATE POLICY policy_guest_visits_kiosk_insert ON guest_visits
    FOR INSERT
    WITH CHECK (member_id = current_setting('app.current_member_id')::uuid);

CREATE POLICY policy_guest_visits_admin ON guest_visits
    FOR ALL
    USING (current_setting('app.current_training_level')::int >= 4);
