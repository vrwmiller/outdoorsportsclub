-- Migration: 0019_create_consumable_items
-- Description: Creates the consumable_items catalog table so that item names and
--              prices are managed server-side rather than accepted from kiosk
--              request bodies. Adds a nullable item_id FK to consumable_purchases
--              for audit traceability. Pre-existing purchase rows have no
--              catalog entry and correctly receive NULL.

CREATE TABLE IF NOT EXISTS consumable_items (
    id               UUID    NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    name             TEXT    NOT NULL,
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents > 0),
    is_active        BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_consumable_items_is_active ON consumable_items (is_active);

ALTER TABLE consumable_purchases
    ADD COLUMN IF NOT EXISTS item_id UUID REFERENCES consumable_items(id);

CREATE INDEX IF NOT EXISTS idx_consumable_purchases_item_id
    ON consumable_purchases (item_id);
