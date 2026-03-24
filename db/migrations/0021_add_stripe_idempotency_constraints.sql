-- Migration: 0021_add_stripe_idempotency_constraints
-- Description: Adds partial unique indexes on stripe_payment_intent_id for
--              consumable_purchases and guest_visits to prevent double-recording
--              a charge when a Stripe Terminal PaymentIntent is retried or
--              replayed. Partial (WHERE IS NOT NULL) because Cash rows have no
--              payment intent and must not be constrained against each other.

CREATE UNIQUE INDEX IF NOT EXISTS uq_consumable_purchases_stripe_intent
    ON consumable_purchases (stripe_payment_intent_id)
    WHERE stripe_payment_intent_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_guest_visits_stripe_intent
    ON guest_visits (stripe_payment_intent_id)
    WHERE stripe_payment_intent_id IS NOT NULL;
