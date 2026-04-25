# Copilot Instructions

This file defines baseline behavior for GitHub Copilot when generating, reviewing, or modifying code in this repository.

These rules are global and apply across all languages, files, and workflows.

---

## General Principles

- Be concise, direct, and technically accurate
- Prefer clarity over cleverness
- Follow existing project patterns unless explicitly instructed otherwise
- Do not introduce new frameworks, patterns, or dependencies without justification
- Do not assume intent — verify against code and documentation

---

## Source of Truth

- `.github/instructions/core.instructions.md` — universal invariants, engineering values, and PR workflow; applies to all files
- Applicable `.github/instructions/*.instructions.md` files — domain-specific rules for the file type being edited
- `docs/design.md` — canonical source for API contracts, schema, and system behavior
- `docs/architecture.md` — system structure and data flow
- `docs/stack-decisions.md` — locked technology choices and tradeoffs

If code, comments, or suggestions conflict with these sources:
- Treat applicable `.github/instructions/` files as authoritative for repository-wide workflow, security, and implementation constraints
- Treat the docs as authoritative for design details that do not conflict with repository instruction files
- Flag the inconsistency instead of guessing

---

## Code Generation Guidelines

- Follow existing naming conventions, file structure, and patterns
- Write minimal, focused changes — avoid unrelated modifications
- Do not add comments unless they clarify non-obvious logic
- Do not add debug/trace logging, temporary debugging code, or TODOs unless requested; add required structured error or audit logging when repository instructions require it
- Prefer explicit, readable logic over abstraction

---

## Reviews and Suggestions

- Validate all suggestions against:
  - current file contents
  - relevant documentation
  - existing project patterns

- Classify suggestions as:
  - **Valid** — correct and should be implemented
  - **Rejected** — incorrect or contradicts project standards
  - **Ambiguous** — insufficient information; request clarification

- Do not assume reviewer correctness — verify claims

---

## Security and Safety

- Do not introduce:
  - hardcoded secrets
  - overly permissive IAM policies
  - wildcard (`*`) access in production contexts, except for the approved **Amazon SNS** direct-to-phone SMS pattern: `Action: sns:Publish`, `Resource: "*"`, with `Condition: StringEquals: { sns:DestinationType: PhoneNumber }`
- Validate input handling and authentication logic where relevant
- Prefer least-privilege and explicit access control, including condition-scoping any approved exception

---

## Git and PR Behavior

- Write clear, concise commit messages
- Keep commits scoped to a single logical change
- Do not combine unrelated changes into one commit
- Do not modify files outside the requested scope

---

## Documentation

- Keep documentation consistent with code changes
- Do not invent undocumented behavior
- If information is missing or unclear, flag it instead of guessing

---

## Style and Formatting

- Follow project linting rules
- Maintain consistent formatting across files
- Do not reformat entire files unless explicitly requested

---

## Emoji Policy

Emojis must **not** be used in any of the following:

- Code
- Comments in code
- Commit messages
- Pull request titles or descriptions
- Review comments or replies
- Documentation

Use plain, professional language at all times.

---

## When Uncertain

- State what is unknown
- Identify the missing information
- Do not infer behavior or fabricate details
- Ask for clarification if needed