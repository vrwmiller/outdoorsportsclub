-- Migration: 0025_extend_members_profile
-- Description: Adds name, date of birth, mailing address, notification email,
--              and notification preference columns to the members table.

ALTER TABLE members ADD COLUMN IF NOT EXISTS first_name       TEXT;
ALTER TABLE members ADD COLUMN IF NOT EXISTS last_name        TEXT;
ALTER TABLE members ADD COLUMN IF NOT EXISTS date_of_birth    DATE;
ALTER TABLE members ADD COLUMN IF NOT EXISTS street_address   TEXT;
ALTER TABLE members ADD COLUMN IF NOT EXISTS city             TEXT;
ALTER TABLE members ADD COLUMN IF NOT EXISTS state            CHAR(2);
ALTER TABLE members ADD COLUMN IF NOT EXISTS zip              TEXT;
ALTER TABLE members ADD COLUMN IF NOT EXISTS notification_email TEXT;
ALTER TABLE members ADD COLUMN IF NOT EXISTS notify_email     BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE members ADD COLUMN IF NOT EXISTS notify_sms       BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE members ADD COLUMN IF NOT EXISTS notify_push      BOOLEAN NOT NULL DEFAULT FALSE;
