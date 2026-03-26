-- Migration: 0023_extend_activity_type_check_auth_reset
-- Description: Adds 'Auth-Reset' to the activity_logs.activity_type CHECK constraint.
--              Required by the admin/members-reset-auth handler which inserts an
--              'Auth-Reset' audit row on every successful authentication reset.
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
        'Auth-Reset'
    ));
