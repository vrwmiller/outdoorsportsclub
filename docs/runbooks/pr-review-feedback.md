# Runbook: Processing Copilot PR Review Feedback

**Audience:** Developers and Webmaster.

This runbook defines how to handle Copilot reviewer feedback on pull requests.

---

## Default policy

Copilot reviewer suggestions are the default path. Prefer accepting and implementing suggestions unless one of these conditions is true:

* The suggestion conflicts with real application operations, runtime behavior, or deployment constraints
* The suggestion degrades user experience for the intended flow
* The suggestion introduces a concrete security weakness or vulnerability

---

## Rejection standard

When rejecting a Copilot suggestion, provide specific evidence in the reply:

* Reference the exact file path and section, or the concrete runtime behavior that contradicts the suggestion
* Keep the reply factual and concise
* Do not reject based on preference alone

---

## Workflow note

Use the PR review workflow in `.github/prompts/review.prompt.md` and the review section in `.github/instructions/pr.instructions.md` as the authoritative implementation procedure.
