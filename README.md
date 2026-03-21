# Outdoor Sports Club

A web application for a ~2,200-member outdoor sporting club. It modernizes the club's web presence, facility, and range operations by digitizing member management, reducing cash handling, freeing RSOs from administrative tasks so they can focus on the range, and enforcing club rules through digital access controls.

## What it does

* **Club Website** — Public home page: club, facility, and membership information
* **Member Portal** — Social login (Google/Facebook), dues payment, QR badge, training-level-gated range access
* **Admin Portal** — Finance, membership management, range operations (Level 4–6 staff)
* **Range Kiosk** — Tablet check-in via QR badge scan, guest fees (Cash, NFC, or card), mandatory waiver re-signing
* **RBAC** — Seven training levels (Guest → Webmaster) control access to every surface

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

## Developer setup

Install these tools once on your machine before working with this repository.

### Required

| Tool | Install | Purpose |
| :--- | :--- | :--- |
| [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2-mac.html) | `brew install awscli` | Deploy CloudFormation stacks, invoke Lambda |
| [gh CLI](https://cli.github.com/) | `brew install gh` | Open PRs, manage issues, check CI status |
| Python 3.12+ | `brew install python@3.12` or existing `python3` (must be 3.12+, check with `python3 --version`) | Required by `env.sh` to create the project venv |

Configure the AWS CLI with the project profile:

```bash
aws configure --profile outdoorsportsclub
# Default region: us-east-1
# Default output: json
```

### Python dev environment

`env.sh` creates a project `.venv` and installs `ruff`, `cfn-lint`, `boto3`, and `stripe` — used for Python linting and Pylance import resolution.

Run once to create or update the venv:

```bash
source env.sh
```

Must be **sourced** (not executed as a subshell) so `.venv` activation propagates to your shell. Requires Python 3.12 or later. Override the interpreter with `PYTHON=python3.12 source env.sh`.

In a new shell where the venv is already set up, activate it directly:

```bash
source .venv/bin/activate
```

## Repeatable workflows

### Lint CloudFormation templates

Run before committing any change to `infra/`:

```bash
cfn-lint infra/stacks/*.yaml
```

Exit 0 = clean. Warnings (W-prefix) are advisory; errors (E-prefix) must be fixed before committing.

### Deploy a CloudFormation stack

```bash
aws cloudformation deploy \
  --stack-name osc-<domain>-<env> \
  --template-file infra/stacks/<template>.yaml \
  --parameter-overrides Environment=<env> [Key=Value ...] \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1 \
  --profile outdoorsportsclub
```

Examples:

```bash
# Deploy KMS keys to dev
aws cloudformation deploy \
  --stack-name osc-kms-dev \
  --template-file infra/stacks/kms.yaml \
  --parameter-overrides Environment=dev \
  --region us-east-1 \
  --profile outdoorsportsclub

# Deploy Cognito User Pool to prod (social provider secrets are passed as parameters)
aws cloudformation deploy \
  --stack-name osc-cognito-prod \
  --template-file infra/stacks/cognito.yaml \
  --parameter-overrides \
      Environment=prod \
      GoogleClientId=<id> \
      GoogleClientSecret=<secret> \
      FacebookAppId=<id> \
      FacebookAppSecret=<secret> \
      CallbackUrl=https://outdoorsportsclub.com/auth/callback \
      LogoutUrl=https://outdoorsportsclub.com \
      UserPoolDomainPrefix=osc-members-prod-<suffix> \
  --region us-east-1 \
  --profile outdoorsportsclub
```

Stacks depend on each other — deploy in this order per environment:

```text
kms → sns → cognito → secrets → s3 → aurora → backup → iam/ → api → route53
```

### Run a DB migration

> **Note:** `db/migrations/` does not exist yet — it will be added in Phase 4. This workflow applies once that directory is introduced.

Migrations use the RDS Data API — no VPN or bastion host required. Aurora must be running and the `osc/dev/aurora-master` secret must exist in Secrets Manager.

```bash
aws rds-data execute-statement \
  --resource-arn <cluster-arn> \
  --secret-arn <aurora-master-secret-arn> \
  --database osc \
  --sql "$(cat db/migrations/<file>.sql)" \
  --region us-east-1 \
  --profile outdoorsportsclub
```

Migrations are numbered and idempotent (`IF NOT EXISTS` guards). Run them in sequence — never skip.

### Open a PR

```bash
git checkout -b feat/<topic>
# ... make changes, commit ...
git push -u origin feat/<topic>
gh pr create --title "feat: description" --body-file /tmp/pr-body.txt --base main
```

See [.github/instructions/pr.instructions.md](.github/instructions/pr.instructions.md) for branch naming rules, PR title format, and the pre-merge checklist.

## Contributing

All changes go on a feature branch and merge via pull request — see [.github/instructions/pr.instructions.md](.github/instructions/pr.instructions.md) for branch naming, PR format, and the pre-merge checklist.

## License

[GPL v3](LICENSE) — Copyright (C) 2026 Outdoor Sports Club Contributors
