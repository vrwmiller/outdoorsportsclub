-- 0022_add_waitlist_position_unique.sql
-- Closes the waitlist position race condition in POST /v1/kiosk/check-in.
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
-- The WHERE clause restricts uniqueness to active rows only; Checked-In and
-- Removed rows may legitimately share position numbers with newer entries on
-- subsequent waitlist cycles.

BEGIN;

CREATE UNIQUE INDEX IF NOT EXISTS uq_wait_list_range_position_active
    ON wait_list (range_id, position)
    WHERE status IN ('Waiting', 'Called');

COMMIT;
