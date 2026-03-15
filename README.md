# Outdoor Sports Club

A web application for a ~2,200-member outdoor sporting club. It modernizes the club's web presence, facility, and range operations by digitizing member management, reducing cash handling, freeing RSOs from administrative tasks so they can focus on the range, and enforcing club rules through digital access controls.

## What it does

- **Club Website** — Public home page: club, facility, and membership information
- **Member Portal** — Social login (Google/Facebook), dues payment, QR badge, training-level-gated range access
- **Admin Portal** — Finance, membership management, range operations (Level 4–6 staff)
- **Range Kiosk** — Tablet check-in via QR badge scan, guest fees (Cash, NFC, or card), mandatory waiver re-signing
- **RBAC** — Seven training levels (Guest → Webmaster) control access to every surface

## Tech stack

| Layer | Technology |
| :--- | :--- |
| Frontend | Next.js (App Router), Tailwind CSS, AWS Amplify Gen 2 |
| Backend | Python AWS Lambda, API Gateway |
| Database | Amazon Aurora Serverless v2 (PostgreSQL), RDS Data API |
| Auth | AWS Cognito (Social Login + Device Token for kiosks) |
| Payments | Stripe Terminal SDK (NFC + card reader), Stripe.js (online dues) |
| Storage | Amazon S3 + Object Lock (waivers, KMS encrypted) |
| Infra | CloudFormation, multi-region capable via `RegionList` parameter |

## Repository layout

```text
.github/       Agents, instructions, and workflow config
docs/          Design docs and architecture diagram

# Planned (to be added during implementation)
functions/     Python Lambda handlers (one file per endpoint)
src/           Next.js frontend
db/migrations/ PostgreSQL migrations
infra/         CloudFormation templates
tests/         Lambda unit tests (pytest + moto)
e2e/           Playwright end-to-end tests
```

## Documentation

| Doc | Purpose |
| :--- | :--- |
| [docs/one-pager.md](docs/one-pager.md) | Executive summary and ROI overview |
| [docs/proposal.md](docs/proposal.md) | Full project proposal |
| [docs/design.md](docs/design.md) | Authoritative technical spec (RBAC, schema, HA/DR) |
| [docs/architecture.md](docs/architecture.md) | System architecture diagram |
| [docs/stack-decisions.md](docs/stack-decisions.md) | Technology selection rationale |

## Contributing

All changes go on a feature branch and merge via pull request — see [.github/instructions/pr.instructions.md](.github/instructions/pr.instructions.md) for branch naming, PR format, and the pre-merge checklist.

## License

[GPL v3](LICENSE) — Copyright (C) 2026 Outdoor Sports Club Contributors
