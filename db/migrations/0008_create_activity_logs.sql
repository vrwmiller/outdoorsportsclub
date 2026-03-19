-- Migration: 0008_create_activity_logs
-- Description: Creates the activity_logs table — immutable audit log for all member activity.
--              Uses BIGINT identity PK for high-volume append workload.

CREATE TABLE IF NOT EXISTS activity_logs (
    id                       BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    member_id                UUID        NOT NULL REFERENCES members (id),
    actor_member_id          UUID        REFERENCES members (id),
    device_id                UUID        REFERENCES devices (id),
    activity_type            TEXT        NOT NULL
                                             CHECK (activity_type IN (
                                                 'Range-Checkin',
                                                 'Range-Checkout',
                                                 'Guest-Payment',
                                                 'Waiver-Signed',
                                                 'Level-Change',
                                                 'Dues-Payment',
                                                 'Service-Hours-Update'
                                             )),
    lane_id                  UUID        REFERENCES lanes (id),
    stripe_payment_intent_id TEXT,
    payment_method           TEXT        CHECK (payment_method IN ('NFC', 'Card', 'Cash')),
    guest_id                 UUID        REFERENCES guests (id),
    waiver_s3_key            TEXT,
    timestamp                TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_activity_logs_member_id     ON activity_logs (member_id);
CREATE INDEX IF NOT EXISTS idx_activity_logs_timestamp     ON activity_logs (timestamp);
CREATE INDEX IF NOT EXISTS idx_activity_logs_activity_type ON activity_logs (activity_type);
CREATE INDEX IF NOT EXISTS idx_activity_logs_device_id     ON activity_logs (device_id);
