-- Migration: 0014_seed_ranges
-- Description: Seeds the five physical ranges. All seed as closed (is_open = FALSE).
--              min_training_level for non-Rifle-Pistol ranges is provisional —
--              confirm values with club leadership before go-live.

INSERT INTO ranges (name, is_open, min_training_level) VALUES
    ('Rifle-Pistol',    FALSE, 1),
    ('Skeet-Trap',      FALSE, 1),   -- TODO: confirm min_training_level with club leadership
    ('Air-Rifle',       FALSE, 1),   -- TODO: confirm min_training_level with club leadership
    ('Indoor-Archery',  FALSE, 1),   -- TODO: confirm min_training_level with club leadership
    ('Outdoor-Archery', FALSE, 1)    -- TODO: confirm min_training_level with club leadership
ON CONFLICT (name) DO NOTHING;
