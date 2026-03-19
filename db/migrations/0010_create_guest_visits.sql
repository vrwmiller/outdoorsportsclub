-- Migration: 0010_create_guest_visits
-- Description: Creates the guest_visits table — one row per range visit per guest.
--              Used to enforce the 2-visit-per-calendar-year annual limit per guest-member pair.

CREATE TABLE IF NOT EXISTS guest_visits (
    id                       UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    guest_id                 UUID        NOT NULL REFERENCES guests (id),
    member_id                UUID        NOT NULL REFERENCES members (id),
    range_id                 UUID        NOT NULL REFERENCES ranges (id),
    lane_id                  UUID        REFERENCES lanes (id) ON DELETE SET NULL,
    visited_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    stripe_payment_intent_id TEXT,
    payment_method           TEXT        NOT NULL CHECK (payment_method IN ('NFC', 'Card', 'Cash'))
);

-- Annual limit check: WHERE guest_id = $1 AND member_id = $2 AND visited_at >= year_start AND visited_at < year_end
CREATE INDEX IF NOT EXISTS idx_guest_visits_guest_member_visited ON guest_visits (guest_id, member_id, visited_at);
-- Sponsor history lookup.
CREATE INDEX IF NOT EXISTS idx_guest_visits_member_id            ON guest_visits (member_id);
