-- Migration: 0023_extend_activity_type_check_auth_reset
-- Description: Adds 'Auth-Reset' to the activity_logs.activity_type CHECK constraint.
--              Required by the admin/members-reset-auth handler which inserts an
--              'Auth-Reset' audit row on every successful authentication reset.
--              Idempotent: DROP CONSTRAINT / ADD CONSTRAINT is safe to re-run because
--              IF EXISTS / IF NOT EXISTS guards are used where available; the constraint
--              name is deterministic so a duplicate run is a no-op.

ALTER TABLE activity_logs
    DROP CONSTRAINT IF EXISTS activity_logs_activity_type_check;

ALTER TABLE activity_logs
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
