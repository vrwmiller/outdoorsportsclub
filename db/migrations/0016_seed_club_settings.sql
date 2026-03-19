-- Migration: 0016_seed_club_settings
-- Description: Seeds the club_settings singleton row with a placeholder annual dues amount.
--              Update annual_dues_cents before go-live — confirm with club leadership.

INSERT INTO club_settings (singleton, annual_dues_cents)
VALUES (TRUE, 7500)   -- $75.00 placeholder — TODO: confirm with club leadership
ON CONFLICT (singleton) DO NOTHING;
