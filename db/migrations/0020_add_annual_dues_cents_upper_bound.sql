-- Migration: 0020_add_annual_dues_cents_upper_bound
-- Description: Adds an upper-bound CHECK constraint to club_settings.annual_dues_cents
--              to prevent accidental or malicious fat-finger entries above $999.99.
--              The handler already enforces this at the application layer; this constraint
--              is a defense-in-depth measure at the DB layer.

ALTER TABLE club_settings
    ADD CONSTRAINT chk_annual_dues_cents_max CHECK (annual_dues_cents <= 99999);
