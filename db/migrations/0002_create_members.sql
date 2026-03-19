-- Migration: 0002_create_members
-- Description: Creates the members table — core identity, training level, dues, and waiver tracking.

CREATE TABLE IF NOT EXISTS members (
    id                  UUID         NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    member_num          TEXT         NOT NULL,
    email               TEXT         NOT NULL,
    training_level      SMALLINT     NOT NULL DEFAULT 0
                                         CHECK (training_level BETWEEN 0 AND 6),
    social_provider_id  TEXT,
    service_hours       DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    waiver_signed_at    TIMESTAMPTZ,
    dues_paid_until     DATE,
    home_phone          TEXT,
    mobile_phone        TEXT,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_members_member_num UNIQUE (member_num),
    CONSTRAINT uq_members_email      UNIQUE (email)
);

CREATE INDEX IF NOT EXISTS idx_members_email      ON members (email);
CREATE INDEX IF NOT EXISTS idx_members_member_num ON members (member_num);
