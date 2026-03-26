-- Migration: 0024_extend_activity_type_check_range_settings
-- Description: Adds Range-Status-Change and Settings-Change to the
--              activity_logs.activity_type CHECK constraint.
--
--              Auth-Reset was added in migration 0023_extend_activity_type_check_auth_reset.
--              Range-Status-Change: written by admin/ranges-status when a range is
--                opened or closed.
--              Settings-Change: written by admin/settings-update when club settings
--                (e.g. annual_dues_cents) are updated.
--
-- PostgreSQL does not support ALTER CONSTRAINT ADD value; the constraint must be
-- dropped and recreated with the full value list.
-- Both actions are combined in one ALTER TABLE statement to keep the change atomic
-- and avoid the brief window between DROP and ADD where the constraint is absent.

ALTER TABLE activity_logs
    DROP CONSTRAINT IF EXISTS activity_logs_activity_type_check,
    ADD CONSTRAINT activity_logs_activity_type_check
        CHECK (activity_type IN (
            'Range-Checkin',
            'Range-Checkout',
            'Guest-Payment',
            'Waiver-Signed',
            'Level-Change',
            'Dues-Payment',
            'Service-Hours-Update',
            'Auth-Reset',
            'Range-Status-Change',
            'Settings-Change'
        ));
