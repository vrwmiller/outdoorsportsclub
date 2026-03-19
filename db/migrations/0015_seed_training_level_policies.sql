-- Migration: 0015_seed_training_level_policies
-- Description: Seeds one row per training level (0–6) with max_guests constraints.
--              Level 2 max_guests is provisional — confirm with club leadership before go-live.

INSERT INTO training_level_policies (training_level, max_guests) VALUES
    (0, 0),  -- Guest: cannot sponsor guests
    (1, 0),  -- Probationary: guests not permitted
    (2, 2),  -- Basic Member: provisional — TODO: confirm max_guests with club leadership
    (3, 2),  -- Qualified
    (4, 2),  -- RSO / Instructor
    (5, 2),  -- Administrator
    (6, 2)   -- Webmaster
ON CONFLICT (training_level) DO NOTHING;
