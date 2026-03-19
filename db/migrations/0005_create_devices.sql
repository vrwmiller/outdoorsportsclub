-- Migration: 0005_create_devices
-- Description: Creates the devices table — kiosk tablet identity, pairing state, and auth token.
--              device_token stores a salted hash; never stored in plaintext.

CREATE TABLE IF NOT EXISTS devices (
    id                      UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    device_token            TEXT,
    location_tag            TEXT        NOT NULL,
    range_id                UUID        NOT NULL REFERENCES ranges (id),
    status                  TEXT        NOT NULL DEFAULT 'Pending-Pairing'
                                            CHECK (status IN ('Pending-Pairing', 'Active', 'Revoked')),
    pairing_code            TEXT,
    pairing_code_expires_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_devices_range_id     ON devices (range_id);
CREATE INDEX IF NOT EXISTS idx_devices_device_token ON devices (device_token);
