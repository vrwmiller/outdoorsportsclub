-- Migration: 0025_extend_members_profile
-- Description: Adds name, date of birth, mailing address, notification email,
--              and notification preference columns to the members table.

ALTER TABLE members
    ADD COLUMN IF NOT EXISTS first_name         TEXT,
    ADD COLUMN IF NOT EXISTS last_name          TEXT,
    ADD COLUMN IF NOT EXISTS date_of_birth      DATE,
    ADD COLUMN IF NOT EXISTS street_address     TEXT,
    ADD COLUMN IF NOT EXISTS city               TEXT,
    ADD COLUMN IF NOT EXISTS state              CHAR(2),
    ADD COLUMN IF NOT EXISTS zip                TEXT,
    ADD COLUMN IF NOT EXISTS notification_email TEXT,
    ADD COLUMN IF NOT EXISTS notify_email       BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS notify_sms         BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS notify_push        BOOLEAN NOT NULL DEFAULT FALSE;
