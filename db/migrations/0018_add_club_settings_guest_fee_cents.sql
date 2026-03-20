-- Migration: 0018_add_club_settings_guest_fee_cents
-- Description: Adds guest_fee_cents to the club_settings singleton so the guest
--              fee can be updated by an Administrator without a schema migration.
--              Seeded at 1000 cents ($10.00) — the current club rate.

ALTER TABLE club_settings ADD COLUMN IF NOT EXISTS guest_fee_cents INTEGER NOT NULL DEFAULT 1000 CHECK (guest_fee_cents > 0);
