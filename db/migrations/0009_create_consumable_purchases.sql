-- Migration: 0009_create_consumable_purchases
-- Description: Creates the consumable_purchases table for kiosk sales tracking.
--              member_id is nullable to support guest purchases.

CREATE TABLE IF NOT EXISTS consumable_purchases (
    id                       UUID         NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    member_id                UUID         REFERENCES members (id),
    device_id                UUID         NOT NULL REFERENCES devices (id),
    item_name                TEXT         NOT NULL,
    quantity                 INT          NOT NULL CHECK (quantity > 0),
    unit_price               DECIMAL(6,2) NOT NULL CHECK (unit_price >= 0),
    total                    DECIMAL(8,2) NOT NULL CHECK (total >= 0),
    stripe_payment_intent_id TEXT,
    payment_method           TEXT         NOT NULL CHECK (payment_method IN ('NFC', 'Card', 'Cash')),
    timestamp                TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_consumable_purchases_member_id ON consumable_purchases (member_id);
CREATE INDEX IF NOT EXISTS idx_consumable_purchases_device_id ON consumable_purchases (device_id);
