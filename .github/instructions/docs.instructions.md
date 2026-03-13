---
description: "Use when writing, editing, or reviewing documentation in the docs/ folder. Covers doc roles, locked design decisions, tech stack, and writing conventions for the Outdoor Sports Club project."
applyTo: "docs/**/*.md"
---

# Docs Guidelines — Outdoor Sports Club

## Doc Roles

| File | Audience | Purpose |
| :--- | :--- | :--- |
| `docs/one-pager.md` | Board / non-technical stakeholders | ROI and business case only; no implementation detail |
| `docs/proposal.md` | Club leadership / project sponsors | High-level architecture and capability summary |
| `docs/design.md` | Developers and Webmaster | Authoritative technical spec; source of truth for all build decisions |
| `docs/architecture.md` | Developers and Webmaster | System architecture diagram and flow notes; must stay in sync with `design.md` |
| `docs/stack-decisions.md` | Developers and Webmaster | In-depth analysis of significant technology choices, rejected alternatives, and architectural tradeoffs; records the reasoning behind decisions that are too detailed for `design.md` |

- Canonical implementation detail (schemas, API endpoints, code libraries, locked decisions) belongs in `design.md` only; technical context needed to explain a tradeoff (e.g., cost tables, rejected alternatives) belongs in `stack-decisions.md` — do not duplicate, cross-reference instead
- `one-pager.md` and `proposal.md` should not contradict `design.md`; if they differ, `design.md` wins
- `stack-decisions.md` captures *why* — the analysis, tradeoffs, and rejected paths behind a decision; `design.md` captures *what* — the canonical decision itself. Do not duplicate content between them; cross-reference instead

## Locked Decisions — Do Not Reopen

These have been decided. Do not introduce alternatives or ambiguity around them.

| Area | Decision |
| :--- | :--- |
| Cloud provider | **AWS** (Amplify Gen 2, Lambda, API Gateway, Aurora Serverless v2, Cognito, S3, SNS, KMS, Backup) |
| Frontend framework | **Next.js** hosted via **AWS Amplify Gen 2** |
| Auth | **AWS Cognito** with Social Login (Google/Facebook) for members; Device Token for kiosks |
| Database | **Amazon Aurora Serverless v2** (PostgreSQL) |
| Payment processor | **Stripe Terminal SDK** — Tap to Pay via tablet NFC; no external card reader hardware |
| SMS notifications | **Amazon SNS** |
| QR badge payload | Opaque token (value of `member_num`); generated client-side via `react-qr-code` |
| QR scanning | `html5-qrcode` in the Next.js kiosk view; POSTs to `POST /v1/kiosk/check-in` |
| Waiver storage | **Amazon S3** with S3 Object Lock (Compliance Mode, 7-year retention) |
| Disaster recovery | **AWS Backup** cross-region replication; IaC via **AWS CloudFormation** or **Amplify Gen 2** |

## Writing Conventions

- Refer to the project as **Outdoor Sports Club** (not "OSC" or "the club")
- Refer to training levels as **Level N** (e.g., "Level 3", not "L3") in prose; use `L6` only in table shorthand
- Use **bold** for service names, role names, and UI labels (e.g., **Webmaster**, **AWS Cognito**, **Member Portal**)
- Use `backticks` for column names, field values, code strings, and endpoint paths (e.g., `training_level`, `/v1/kiosk/check-in`)
- Bullet lists use `*` with four-space indent for nested items
- All tables must have a header row and a separator row with `:---` alignment
- One blank line between sections; no double blank lines
