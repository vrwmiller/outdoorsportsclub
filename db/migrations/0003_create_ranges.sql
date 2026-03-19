-- Migration: 0003_create_ranges
-- Description: Creates the ranges table — physical ranges with open/close state and access requirements.

CREATE TABLE IF NOT EXISTS ranges (
    id                 UUID     NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    name               TEXT     NOT NULL,
    is_open            BOOLEAN  NOT NULL DEFAULT FALSE,
    min_training_level SMALLINT NOT NULL DEFAULT 0
                                    CHECK (min_training_level BETWEEN 0 AND 6),
    CONSTRAINT uq_ranges_name UNIQUE (name)
);
