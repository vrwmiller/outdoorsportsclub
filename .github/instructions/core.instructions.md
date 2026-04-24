---
description: "Universal rules that apply to every agent and every file in the Outdoor Sports Club project. All agents must read this file. It consolidates the cross-cutting design invariants and the agent file convention baseline so that each agent does not need to list them individually."
applyTo: "**"
---

# Core Rules — Outdoor Sports Club

All agents must read and apply this file. It does not replace the domain-specific instruction files
(`backend.instructions.md`, `database.instructions.md`, etc.) — those still govern their respective
file scopes. This file captures rules that apply universally, regardless of layer.

---

## Cross-Cutting Design Invariants

These invariants must hold across all design decisions and all agents. They are never up for
re-evaluation without explicit Webmaster approval.

| Invariant | Rule |
| :--- | :--- |
| `training_level` authority | Always re-queried from Aurora via RDS Data API — never read from the JWT claim for access control |
| CORS | `Access-Control-Allow-Origin` must be set from an env var; never `*` in production |
| IAM | No `"Resource": "*"` on data-plane permissions |
| Secrets | Lambda env vars use Secrets Manager ARNs, never plaintext values |
| S3 public access | All buckets have block-public-access enabled; no public bucket policies |
| Device tokens | Stored as HMAC-SHA256 hash only — raw token never persisted; validated with `hmac.compare_digest` |
| PII in `dev` | `dev` Aurora cluster must never contain real member PII — use synthetic test data only |
| Schema changes | Must be backward-compatible; no `DROP TABLE`, `DROP COLUMN`, or `TRUNCATE` in forward migrations |
| API contracts | All routes must be added to `docs/design.md` Section 7 before implementation begins |
| Waiver storage | S3 Object Lock (Compliance Mode, 7-year), KMS encrypted, key recorded in `activity_logs.waiver_s3_key` (member) or `guests.waiver_s3_key` (guest) |

---

## Engineering Values

All agents must apply the engineering values defined in `.github/instructions/values.instructions.md`.
Key principles: Correctness > Convenience; Security by Default; Evidence over Speculation;
Explicit Failure Modes; Bounded Resource Usage; Minimal User Friction (within safety constraints);
Observability.

---

## PR Workflow

All branch, commit, and PR operations for every agent must follow `.github/instructions/pr.instructions.md`.
Key rules:

* Never commit directly to `main`
* Branch names: `feat/<topic>`, `fix/<topic>`, `chore/<topic>` — lowercase, hyphens only
* One logical change per commit; multiple commits per PR encouraged
* PR titles follow commit message convention: `feat:`, `fix:`, or `chore:` prefix
* Use `--body-file` with `gh pr create` / `gh pr edit` — never inline multi-line body in the shell
* Write PR body files using the file-creation tool, not shell heredocs or echo
* Before opening a PR touching `functions/**/*.py` or `db/**/*.sql` or `infra/**/*.yaml`:
  invoke the system agent for a security review and fix any High or Critical findings
* Before opening a PR touching `functions/**/*.py` or `tests/**/*.py`: run `pytest tests/ --tb=short -q` and confirm it passes
* Before opening a PR touching `infra/**/*.yaml`: run `cfn-lint` and confirm no errors
* Before opening a PR touching `src/**/*.ts`, `src/**/*.tsx`, or `src/**/*.css`: run `npm run build` and confirm it passes
* Before opening a PR touching `**/*.md`: run `pymarkdown scan -r docs/ README.md` and confirm no errors

---

## Agent File Conventions

Every agent file (`.github/agents/*.agent.md`) must follow this structure:

```markdown
---
description: "<single-line description used for agent selection>"
tools: [read, search, edit]
---

You are the <role> for the Outdoor Sports Club project. <One-sentence purpose.>

## Stack & Context
...

## Instructions
Always read and apply the following instruction files:
* `.github/instructions/core.instructions.md` — universal invariants, engineering values, and PR workflow
* `.github/instructions/<domain>.instructions.md` — domain-specific conventions for this agent
```

Rules:

* `description` must be a single string — no YAML arrays or multi-line values
* `tools` must include `read` and `search` at minimum; `edit` for agents that write files
* Every agent must have an `## Instructions` section that names the instruction file(s) it must apply
* Every agent **must** include a reference to `.github/instructions/core.instructions.md` — this replaces individual listings of `values.instructions.md` and `pr.instructions.md` in each agent

---

## Instruction File Coverage

Each instruction file governs a specific file scope. When creating or editing files, identify which
instruction files apply:

| Instruction file | `applyTo` scope |
| :--- | :--- |
| `backend.instructions.md` | `functions/**/*.py` |
| `database.instructions.md` | `db/**/*.sql` |
| `designer.instructions.md` | `src/**/*.ts`, `src/**/*.tsx` |
| `docs.instructions.md` | `docs/**/*.md` |
| `infra.instructions.md` | `infra/**/*.yaml`, `infra/**/*.json`, `amplify/**/*.ts`, `amplify/**/*.yaml` |
| `linter.instructions.md` | `**/*.md`, `**/*.ts`, `**/*.tsx`, `**/*.js`, `**/*.jsx`, `**/*.py` |
| `pr.instructions.md` | `**` (all files — branch, commit, PR conventions) |
| `qa.instructions.md` | `tests/**/*.py`, `src/**/*.test.tsx`, `e2e/**/*.ts`, `.github/workflows/*.yml` |
| `security.instructions.md` | `functions/**/*.py`, `db/**/*.sql`, `infra/**/*.yaml`, `src/**/*.ts`, `src/**/*.tsx` |
| `values.instructions.md` | `**` (all files — engineering values apply to every agent and every layer) |
| `core.instructions.md` | `**` (all files — universal invariants and agent conventions) |
| `architect.instructions.md` | `.github/agents/**/*.md`, `.github/instructions/**/*.md` |
