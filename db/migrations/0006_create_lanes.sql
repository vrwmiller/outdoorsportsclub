-- Migration: 0006_create_lanes
-- Description: Creates the lanes table — per-range lane occupancy state with consistency constraints.

CREATE TABLE IF NOT EXISTS lanes (
    id                UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    range_id          UUID        NOT NULL REFERENCES ranges (id),
    lane_number       SMALLINT    NOT NULL,
    status            TEXT        NOT NULL DEFAULT 'Available'
                                      CHECK (status IN ('Available', 'Occupied', 'Closed')),
    guest_count       SMALLINT    NOT NULL DEFAULT 0
                                      CHECK (guest_count BETWEEN 0 AND 2),
    current_member_id UUID        REFERENCES members (id) ON DELETE SET NULL,
    checked_in_at     TIMESTAMPTZ,
    CONSTRAINT uq_lanes_range_lane UNIQUE (range_id, lane_number),
    -- Available/Closed lanes must have no occupant and zero guests.
    -- Occupied lanes must have a sponsoring member and 0-2 guests.
    CONSTRAINT chk_lanes_occupancy CHECK (
        (status IN ('Available', 'Closed')
            AND current_member_id IS NULL
            AND guest_count = 0)
        OR
        (status = 'Occupied'
            AND current_member_id IS NOT NULL
            AND guest_count BETWEEN 0 AND 2)
    )
);

CREATE INDEX IF NOT EXISTS idx_lanes_range_status   ON lanes (range_id, status);
CREATE INDEX IF NOT EXISTS idx_lanes_current_member ON lanes (current_member_id);
