---
description: "Use when creating, editing, or reviewing agent definition files (.github/agents/*.agent.md). Covers agent file conventions, cross-cutting design invariants, and the PR workflow that applies to all agents in the Outdoor Sports Club project."
applyTo: ".github/agents/**/*.md, .github/instructions/**/*.md"
---

# Architect & Agent File Standards — Outdoor Sports Club

## Agent File Conventions (`.github/agents/*.agent.md`)

Every agent file must follow this structure:

```markdown
---
description: "<single-line description used for agent selection>"
tools: [read, search, edit]
---

You are the <role> for the Outdoor Sports Club project. <One-sentence purpose.>

## Stack & Context
...

## Instructions
Always read and apply `.github/instructions/<name>.instructions.md` before implementing or editing any file in this agent's domain. Also follow `.github/instructions/pr.instructions.md` for all branch, commit, and PR operations.
```

Rules:
* `description` must be a single string — no YAML arrays or multi-line values
* `tools` must include `read` and `search` at minimum; `edit` for agents that write files
* Every agent must have an `## Instructions` section that names the instruction file(s) it must apply
* Every agent **must** include a reference to `.github/instructions/pr.instructions.md` — the PR workflow applies to all agents that create branches or commits

## PR Workflow (applies to all agents)

All branch, commit, and PR operations for every agent must follow `.github/instructions/pr.instructions.md`. Key rules:

* Never commit directly to `main`
* Branch names: `feat/<topic>`, `fix/<topic>`, `chore/<topic>` — lowercase, hyphens only
* PR titles follow commit message convention: `feat:`, `fix:`, or `chore:` prefix
* Use `--body-file` with `gh pr create` / `gh pr edit` — never inline multi-line body in the shell
* Write PR body files using the file-creation tool, not shell heredocs

## Cross-Cutting Design Invariants

These invariants must hold across all design decisions and all agents. They are never up for re-evaluation without explicit Webmaster approval:

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

## Instruction File Coverage

Each instruction file governs a specific file scope. When creating or editing files, identify which instruction files apply:

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
| `architect.instructions.md` | `.github/agents/**/*.md`, `.github/instructions/**/*.md` |
