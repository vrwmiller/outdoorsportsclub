# Dev Environment Reset

**Audience:** Developer with AWS CLI access and the `outdoorsportsclub` profile configured.

This runbook resets the rebuildable stacks in the `dev` environment to a clean,
known-good state without touching stateful resources (Aurora, KMS, S3, Secrets,
Cognito, Backup). Use this when the dev environment has drifted, a stack is in a
broken state, or you want to verify the deployment templates work from scratch.

> **dev only.** All destroy targets are blocked on `ENV=prod`.

---

## What this resets

| Stack | Action |
| :--- | :--- |
| `osc-lambda-dev` | Destroyed and redeployed |
| `osc-iam-kiosk-dev` | Destroyed and redeployed |
| `osc-sns-dev` | Destroyed and redeployed |

## What this does NOT touch

Aurora, KMS, Secrets Manager, S3, Cognito, artifacts bucket, and Backup vault are
left intact. No data is lost and no credentials rotate.

---

## Prerequisites

* AWS CLI configured with the `outdoorsportsclub` profile (`us-east-1`)
* Lambda ZIPs are already uploaded to `osc-lambda-artifacts-dev-<account-id>`
  (if not, run `make package upload ENV=dev` first — see the [Lambda code deploy runbook](lambda-code-deploy.md))

---

## Step 1 — Destroy rebuildable stacks

Run in this order. Each command blocks until the stack is fully deleted.

```bash
make destroy-lambda ENV=dev
make destroy-iam-kiosk ENV=dev
make destroy-sns ENV=dev
```

> `destroy-lambda` must run before `destroy-iam-kiosk` because the Lambda stack imports
> the IAM execution role ARN as a CloudFormation cross-stack export. Reversing the
> order produces a `DELETE_FAILED` error.

---

## Step 2 — Rebuild

`deploy-base` is idempotent and skips stacks with no changes. It re-creates SNS
and IAM along with the stateful stacks (which will detect no change and complete
instantly).

```bash
make deploy-base ENV=dev
```

Then redeploy Lambda:

```bash
make deploy-lambda ENV=dev
```

---

## Step 3 — Migrations (conditional)

Migrations are idempotent — safe to re-run. If the schema has not changed since
the last run, re-running is harmless. If you are unsure, run it:

```bash
make migrate ENV=dev
```

---

## Step 4 — Smoke test

```bash
make invoke ENV=dev \
  FUNCTION=osc-kiosk-range-lanes-dev \
  PAYLOAD='{"headers":{"x-device-token":"<token>"},"httpMethod":"GET","path":"/v1/kiosk/range/lanes"}'
```

Expected: HTTP 200 with a JSON body.

---

## Full sequence at a glance

```bash
# Destroy (most-dependent first)
make destroy-lambda ENV=dev
make destroy-iam-kiosk ENV=dev
make destroy-sns ENV=dev

# Rebuild
make deploy-base ENV=dev
make deploy-lambda ENV=dev

# Migrate (if needed)
make migrate ENV=dev

# Smoke test
make invoke ENV=dev FUNCTION=osc-kiosk-range-lanes-dev PAYLOAD='{"httpMethod":"GET","headers":{"x-device-token":"<token>"},"path":"/v1/kiosk/range/lanes"}'
```

---

## Troubleshooting

**`destroy-iam-kiosk` fails with export reference error**
`osc-lambda-dev` still exists. Run `make destroy-lambda ENV=dev` first.

**`deploy-lambda` fails with "role does not exist"**
`deploy-base` did not complete successfully or `osc-iam-kiosk-dev` is still deleting.
Wait for `deploy-base` to finish fully before running `deploy-lambda`.

**`make invoke` returns a `FunctionError` or a non-200 `statusCode` in the response body**
Lambda deployed but the handler is failing at startup. Check CloudWatch Logs:

```bash
aws logs tail /aws/lambda/osc-kiosk-range-lanes-dev --since 5m --profile outdoorsportsclub
```
