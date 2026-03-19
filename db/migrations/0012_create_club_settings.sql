-- Migration: 0012_create_club_settings
-- Description: Creates the club_settings singleton table for club-wide configuration values
--              (e.g., annual dues amount) editable by Administrators without a schema migration.

CREATE TABLE IF NOT EXISTS club_settings (
    singleton            BOOLEAN     NOT NULL DEFAULT TRUE PRIMARY KEY,
    annual_dues_cents    INTEGER     NOT NULL CHECK (annual_dues_cents > 0),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by_member_id UUID        REFERENCES members (id) ON DELETE SET NULL,
    CONSTRAINT chk_club_settings_singleton CHECK (singleton = TRUE)
);
