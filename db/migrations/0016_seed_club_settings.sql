-- Migration: 0016_seed_club_settings
-- Description: Seeds the club_settings singleton row with a placeholder annual dues amount.
--              Update annual_dues_cents before go-live — confirm with club leadership.

-- annual_dues_cents is seeded with an obvious sentinel (1 cent = $0.01) that will
-- never be mistaken for a real dues amount. An Administrator must update this value
-- via the Admin Portal before dues payment flows are enabled.
INSERT INTO club_settings (singleton, annual_dues_cents)
VALUES (TRUE, 1)   -- sentinel — must be updated by Administrator before go-live
ON CONFLICT (singleton) DO NOTHING;
