---
description: "Engineering values that govern all design and implementation decisions in the Outdoor Sports Club project. Apply to every agent, every layer, and every review."
applyTo: "**"
---

# Engineering Values — Outdoor Sports Club

These values govern all design, implementation, and review decisions across every layer of the project. They are not aspirational — they are constraints. When a proposed design or implementation conflicts with a value, resolve the conflict before proceeding.

---

## Correctness > Convenience

- Reject assumptions without validation
- Require explicit error handling for all failure modes that can realistically occur
- Do not accept shortcuts that trade correctness for a shorter code path

**In this project:** `training_level` must always be re-queried from Aurora — reading the JWT claim is a convenience shortcut that violates this value. `unit_price` must be looked up from the DB, not accepted from the request body.

---

## Security by Default

- Treat all external input (request bodies, headers, query strings, QR tokens, device tokens) as untrusted until validated
- Prefer deny-by-default patterns — define what is allowed; reject everything else
- No `"Resource": "*"` on data-plane IAM permissions
- No plaintext secrets in code, env vars, or logs

**In this project:** RLS is the default for all tables. Kiosk device tokens are validated against the `devices` table on every request. The Cognito Authorizer is required on all member routes; access decisions inside Lambda are based on Aurora re-query, not JWT claims.

---

## Evidence over Speculation (Implementation Decisions)

When a claim is used to justify an implementation decision, it must be supported by at least one of:

- A code path (file + line)
- A concrete input that triggers the behavior
- A reproducible failure scenario

> **Scope:** This value governs implementation decisions and code review findings — not exploratory design discussions, where hypothesis and tradeoff analysis naturally precede evidence.

**In this project:** PR review comments that assert a security flaw, incorrect behavior, or performance problem must cite the specific code path or scenario. Speculative findings must be labeled `[SPECULATION]`.

---

## Explicit Failure Modes

Every system boundary must define:

- What happens when the operation fails (error type, HTTP status, user-visible message)
- How the failure is surfaced (log level, response body, CloudWatch alarm)

Silence is not a valid failure mode. An operation that fails silently is a correctness violation.

**In this project:** Missing GUCs for RLS (`app.current_member_id`, `app.current_training_level`) cause silent empty `SELECT` results — violating this value. All Lambda handlers must return structured error responses and log failures at `ERROR` level.

---

## Bounded Resource Usage

No operation should grow unbounded relative to input that the system does not control. This applies to:

- Database queries (always include `LIMIT` or predicate filters that bound the result set)
- Retry loops (always have a maximum retry count and backoff)
- Memory accumulation (never buffer an entire large result set in Lambda memory)

> **Scope:** "Unbounded" means unbounded relative to external input, not relative to total dataset size. This project's member counts are inherently small; the concern is queries or loops whose cost scales with adversarial or malformed input.

**In this project:** Lambda has a hard memory and time limit. Aurora query cost directly affects ACU billing. Unbounded queries on `activity_logs` (high-volume append-only table) are a real cost risk.

---

## Minimal User Friction (Within Safety Constraints)

- Minimize steps required to complete core tasks — especially on the Kiosk (time-constrained, semi-public) and Admin Portal (operational efficiency)
- Prefer sensible defaults over requiring configuration input
- Surface errors clearly without blocking progress when it is safe to let the user continue
- Avoid unnecessary confirmation prompts for low-risk, reversible actions

### Constraints — these are hard limits

- Must **NOT** weaken security controls (no skipping auth steps for UX convenience)
- Must **NOT** hide or suppress critical errors (errors that affect data integrity must always be visible)
- Must **NOT** introduce implicit behavior that reduces correctness (no silent fallbacks that produce wrong results)

**In this project:** The kiosk is operated by members under time pressure; check-in and waiver flows must be as short as possible while preserving all auth and safety checks.

---

## Observability

Failures that cannot be detected in production are equivalent to failures that are not handled. Every layer must emit enough structured signal to diagnose problems without a code deploy.

- All Lambda handlers log structured `ERROR` entries with request context (member ID or device ID, route, timestamp) on any unhandled exception or 5xx response
- Payment flows log Stripe event IDs and DB write outcomes so a "payment posted, no DB row" scenario can be diagnosed from CloudWatch alone
- S3 waiver upload failures log the attempted key and the error — never silently discard a waiver
- CloudWatch alarms exist for Lambda error rate and Aurora ACU spikes
- No debug or trace logging in production that includes PII (member name, email, phone)

**In this project:** There is currently no defined behavior for kiosk-side S3 upload failures or mid-transaction Stripe errors. Explicit failure handling and logging for these paths is a known gap to be addressed.
