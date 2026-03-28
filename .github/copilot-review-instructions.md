# Copilot Code Review Instructions (Loop-Resistant Version)

## Primary Objective

Identify **high-confidence, actionable issues only** in these categories:

- **Security vulnerabilities** — injection, auth bypass, insecure secrets handling, OWASP Top 10
- **Correctness bugs** — runtime errors, broken behavior, incorrect logic, data loss risks
- **Accessibility blockers** — WCAG A/AA violations that prevent completion of core user flows

If an issue does **not clearly meet one of these categories, do not comment.**

---

## Review Decision Gate (MANDATORY)

Before raising any issue, all of the following must be true:

1. **Category match**  
   The issue clearly falls into one of the allowed categories above.

2. **Concrete evidence**  
   You can point to:
   - specific line(s) of code  
   - a clear execution path or failure mode

3. **Deterministic impact**  
   The issue results in one of:
   - exploitable condition  
   - runtime failure  
   - broken user flow  
   - guaranteed incorrect behavior  

   ⚠️ If the impact is speculative, uncertain, or “might”, **do not comment**.

4. **Actionable fix**  
   You can suggest a **specific, minimal change** to resolve it.

If any of the above fail → **DO NOT COMMENT**

---

## Explicit Non-Goals (Hard Exclusions)

Do **NOT** comment on:

- Code style, formatting, linting, naming, or file structure
- Hypothetical edge cases without a reproducible path
- “Best practices” without a demonstrated failure or vulnerability
- Performance optimizations unless they cause correctness issues
- Design or architecture decisions already documented in:
  - `docs/`
  - `designer.instructions.md`
- Missing features or enhancements outside PR scope
- Placeholder or stub pages marked “coming soon”
- Authentication on scaffolding intentionally deferred
- CSS/theming/token alignment
- Logging strategy (e.g., `console.error` vs throwing in `"use client"`)

---

## Deduplication & Loop Prevention

- **Do not repeat** issues already raised earlier in the review
- **Do not re-flag** issues marked as resolved in the PR conversation
- If a previous comment was addressed but not perfectly:
  - Only respond if the issue still meets **all Decision Gate criteria**
- Do not rephrase the same issue with different wording

---

## Severity Threshold

Only report issues that meet **at least one**:

- Security risk with plausible exploit path
- Code will throw, crash, or fail at runtime
- Data corruption or loss is possible
- A user cannot complete a primary flow (accessibility)

If the issue is minor, cosmetic, or non-blocking → **DO NOT COMMENT**

---

## Output Format (Strict)

For each issue:

- **Category:** (Security | Correctness | Accessibility)  
- **Location:** file + line(s)  
- **Problem:** concise, factual description  
- **Impact:** concrete failure or exploit scenario  
- **Fix:** minimal actionable change  

If no issues meet criteria, respond with:

> ✅ No blocking issues found in scope.

---

## Termination Condition (Critical)

If you cannot find a qualifying issue after reviewing the PR:

- **Stop immediately**
- Do not continue searching for weaker issues
- Do not broaden scope

---

## Anti-Pattern Guardrails

Do NOT:

- Infer intent beyond the code
- Assume missing context
- Suggest refactors disguised as “bugs”
- Expand scope mid-review

---

## Meta Rule

When in doubt:

> **Silence is preferred over low-confidence feedback**