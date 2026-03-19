-- Migration: 0007_create_guests
-- Description: Creates the guests table — persistent identity for non-member visitors.
--              Reused across visits so a valid waiver on file does not need to be re-signed.

CREATE TABLE IF NOT EXISTS guests (
    id               UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    first_name       TEXT        NOT NULL,
    last_name        TEXT        NOT NULL,
    phone            TEXT        NOT NULL,
    email            TEXT        NOT NULL,
    waiver_signed_at TIMESTAMPTZ,
    waiver_s3_key    TEXT,
    CONSTRAINT uq_guests_identity UNIQUE (first_name, last_name, phone, email)
);

-- Kiosk lookup during the guest add-on step.
CREATE INDEX IF NOT EXISTS idx_guests_lookup ON guests (last_name, phone, email);
