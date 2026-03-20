-- Migration: 0017_add_members_waiver_version
-- Description: Adds waiver_version to members so the kiosk waiver handler can
--              track how many times a member has signed (or re-signed) a waiver.
--              Defaults to 0 for all existing rows; incremented to 1 on first sign.

ALTER TABLE members ADD COLUMN IF NOT EXISTS waiver_version INT NOT NULL DEFAULT 0;
