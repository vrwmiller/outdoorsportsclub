# Copilot Code Review Instructions

Focus ONLY on the following categories:

- **Security vulnerabilities** — injection, auth bypass, insecure secrets handling, OWASP Top 10
- **Correctness bugs** — runtime errors, broken behavior, incorrect logic, data loss risks
- **Accessibility blockers** — WCAG A/AA violations that prevent users from completing core flows

## Do NOT comment on

- Code style, formatting, or semicolon/punctuation conventions (enforced by ESLint/Prettier)
- Placeholder or stub pages explicitly marked "coming soon" or deferred to a follow-up PR
- Design or architecture decisions already documented in `docs/` or `designer.instructions.md`
- Issues already addressed and resolved in prior review thread replies on the same PR
- Missing features or enhancements not in scope for the current PR
- Authentication gates on scaffold placeholders — auth is added in dedicated follow-up PRs
- CSS token alignment or theme choices — those belong in a dedicated theme PR
- `console.error` vs throwing in `"use client"` modules — throwing crashes the React tree; `console.error` is intentional
