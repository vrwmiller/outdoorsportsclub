-- Migration: 0023_extend_activity_type_check_auth_reset
-- Description: Defines the complete activity_logs.activity_type CHECK constraint
--              with all current valid values, including 'Auth-Reset' (written by
--              admin/members-reset-auth), 'Range-Status-Change' (written by
--              admin/ranges-status), and 'Settings-Change' (written by
--              admin/settings-update).
--
--              All values are defined here rather than split across 0023 and 0024
--              to prevent a transient constraint-narrowing window during deployment:
--              scripts/migrate.py applies migrations sequentially on every run, so
--              an 0023-only constraint (lacking the newer types) would be live briefly
--              between the two files executing, causing concurrent handlers to fail
--              CHECK validation.
--
--              Idempotent: re-running will drop and re-add the constraint, which is
--              safe and non-destructive. DROP and ADD are combined in a single ALTER
--              TABLE statement to minimise lock time. Dollar-quoted procedural blocks
--              are intentionally avoided — scripts/migrate.py splits on semicolons.

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
