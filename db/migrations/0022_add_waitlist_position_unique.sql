-- Migration: 0022_add_waitlist_position_unique
-- Description: Closes the waitlist position race condition in POST /v1/kiosk/check-in.
--
-- When the range is full, the check-in handler computes MAX(position)+1 and
-- then INSERTs a wait_list row.  Under READ COMMITTED, two concurrent requests
-- can read the same MAX and both attempt to INSERT with the same (range_id,
-- position) pair, violating the intended queue ordering.
--
-- This migration adds two guards:
--   1. A partial unique index that makes duplicate active positions impossible
--      at the DB layer regardless of isolation level (belt-and-suspenders).
--   2. The handler is updated to use SERIALIZABLE isolation so the conflict is
--      detected at commit-time and the loser gets SQLSTATE 40001, not a silent
--      FK or ordering anomaly.
--
-- The WHERE clause restricts uniqueness to active rows only; rows with terminal
-- statuses like Checked-In, Expired, or Cancelled may legitimately share
-- position numbers with newer entries on subsequent waitlist cycles.
--
-- Before adding the unique index, normalise any historical duplicates so the
-- index creation cannot fail on existing environments.  For each (range_id,
-- position) pair with multiple active rows (Waiting or Called), we keep the
-- earliest-joined row (using id as a deterministic tie-breaker) and mark the
-- others as Cancelled (a terminal status that is excluded from the partial
-- index).  This statement is idempotent: once there are no duplicate active
-- positions, it becomes a no-op on subsequent runs.

WITH ranked AS (
    SELECT
        id,
        row_number() OVER (
            PARTITION BY range_id, position
            ORDER BY joined_at, id
        ) AS rn
    FROM wait_list
    WHERE status IN ('Waiting', 'Called')
)
UPDATE wait_list w
SET status = 'Cancelled'
WHERE w.id IN (
    SELECT id
    FROM ranked
    WHERE rn > 1
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_wait_list_range_position_active
    ON wait_list (range_id, position)
    WHERE status IN ('Waiting', 'Called');
