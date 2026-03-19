-- Migration: 0004_create_training_level_policies
-- Description: Creates the training_level_policies table — one row per training level with
--              scalar constraints (e.g., max guests per range visit) configurable by Administrators.

CREATE TABLE IF NOT EXISTS training_level_policies (
    training_level SMALLINT NOT NULL CHECK (training_level BETWEEN 0 AND 6) PRIMARY KEY,
    max_guests     SMALLINT NOT NULL CHECK (max_guests >= 0)
);
