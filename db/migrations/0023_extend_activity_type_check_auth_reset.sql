-- Migration: 0023_extend_activity_type_check_auth_reset
-- Description: Adds 'Auth-Reset' to the activity_logs.activity_type CHECK constraint.
--              Required by the admin/members-reset-auth handler which inserts an
--              'Auth-Reset' audit row on every successful authentication reset.
--              Idempotent: the DO $$ block checks pg_constraint to confirm
--              'Auth-Reset' is not already present before altering the table,
--              so repeated runs skip the DROP/ADD entirely and take no lock.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM   pg_constraint c
        JOIN   pg_class      t ON t.oid = c.conrelid
        WHERE  c.conname = 'activity_logs_activity_type_check'
          AND  c.contype = 'c'
          AND  t.relname = 'activity_logs'
          AND  pg_get_constraintdef(c.oid) LIKE '%Auth-Reset%'
    ) THEN
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
    END IF;
END $$;
