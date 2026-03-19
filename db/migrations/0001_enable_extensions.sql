-- Migration: 0001_enable_extensions
-- Description: Enables the pgcrypto extension required for gen_random_uuid().

CREATE EXTENSION IF NOT EXISTS pgcrypto;
