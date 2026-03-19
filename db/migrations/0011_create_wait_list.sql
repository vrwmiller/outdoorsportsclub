-- Migration: 0011_create_wait_list
-- Description: Creates the wait_list table — queued members waiting for an available lane.

CREATE TABLE IF NOT EXISTS wait_list (
    id          UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    range_id    UUID        NOT NULL REFERENCES ranges (id),
    member_id   UUID        NOT NULL REFERENCES members (id),
    device_id   UUID        NOT NULL REFERENCES devices (id),
    guest_count SMALLINT    NOT NULL DEFAULT 0 CHECK (guest_count BETWEEN 0 AND 2),
    position    SMALLINT    NOT NULL,
    status      TEXT        NOT NULL
                                CHECK (status IN ('Waiting', 'Called', 'Expired', 'Cancelled', 'Checked-In')),
    joined_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    called_at   TIMESTAMPTZ,
    expires_at  TIMESTAMPTZ
);

-- A member may not hold more than one active position in the queue for the same range.
-- Partial unique index — PostgreSQL does not support filtered UNIQUE constraints.
CREATE UNIQUE INDEX IF NOT EXISTS idx_wait_list_active_member_range
    ON wait_list (range_id, member_id)
    WHERE status IN ('Waiting', 'Called');

-- Queue advance: WHERE range_id = $1 AND status = 'Waiting' ORDER BY position LIMIT 1
CREATE INDEX IF NOT EXISTS idx_wait_list_range_status_position ON wait_list (range_id, status, position);
-- Member cancellation and status lookup.
CREATE INDEX IF NOT EXISTS idx_wait_list_member_status         ON wait_list (member_id, status);
