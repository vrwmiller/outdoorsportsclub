# Stack Destroy and Rebuild

**Audience:** Developer with AWS CLI access and the `outdoorsportsclub` profile configured.

This runbook covers using the `destroy-*` Makefile targets to delete and rebuild
stateless CloudFormation stacks. Use this to verify a stack template is
self-sufficient, clear a stuck stack that `cloudformation deploy` cannot repair,
or exercise the deployment path from a clean state.

> **dev only.** All destroy targets are blocked on `ENV=prod`. Running any destroy
> target with `ENV=prod` exits immediately with an error.

---

## Which stacks can be destroyed

Only stacks without stateful resources are eligible. There are three Makefile
destroy targets; `osc-iam-admin-<env>` and `osc-iam-member-<env>` can also be
deleted manually when needed:

| Target | Stack deleted | Rebuild command |
| :--- | :--- | :--- |
| `make destroy-lambda` | `osc-lambda-<env>` (Lambda functions + API Gateway) | `make deploy-lambda ENV=<env>` |
| `make destroy-iam-kiosk` | `osc-iam-kiosk-<env>` (Kiosk IAM roles + policies) | `make deploy-base ENV=<env>` |
| *(manual)* | `osc-iam-admin-<env>` (Admin IAM roles + policies) | `make deploy-base ENV=<env>` |
| *(manual)* | `osc-iam-member-<env>` (Member IAM roles + policies) | `make deploy-base ENV=<env>` |
| `make destroy-sns` | `osc-sns-<env>` (SNS topic) | `make deploy-base ENV=<env>` |

> **Note:** There are no `destroy-iam-admin` or `destroy-iam-member` Makefile targets.
> To remove those stacks manually, use `aws cloudformation delete-stack` +
> `aws cloudformation wait stack-delete-complete` (see [Troubleshooting](#troubleshooting)).

**Do not attempt to destroy** the following — they carry `DeletionPolicy: Retain`
and cannot be cleanly cycled without manual cleanup:

* `osc-kms-<env>` — KMS key deletion has a 7–30 day waiting period; existing ciphertext breaks
* `osc-secrets-<env>` — holds the device token salt and DB credentials referenced by Lambda
* `osc-aurora-<env>` — dataset; slow to reprovision
* `osc-s3-<env>` — waiver documents
* `osc-cognito-<env>` — pool IDs are baked into Amplify config and kiosk device configs
* `osc-artifacts-<env>` — Lambda deployment packages
* `osc-backup-<env>` — AWS Backup vault

---

## Prerequisites

* AWS CLI configured with the `outdoorsportsclub` profile (`us-east-1`)
* `ENV` set to `dev` (destroy targets must never run with `ENV=prod`)
* The stacks to be destroyed exist (`aws cloudformation list-stacks` to verify)
* `osc-cognito-<env>` exists — `osc-iam-admin-<env>` and `osc-iam-member-<env>` import the Cognito User Pool ARN; `deploy-base` will fail with a missing-export error if this stack is absent. If the Cognito stack does not exist, first set a valid hosted UI domain prefix (`export USER_POOL_DOMAIN_PREFIX=osc-members-dev-<account-suffix>`), then run `make deploy-cognito ENV=dev`.

---

## Dependency order

`osc-lambda-<env>` imports exports from `osc-iam-kiosk-<env>` (the execution role ARN)
and also imports `osc-sns-admin-alerts-arn-<env>` from `osc-sns-<env>` (as the
`SNS_ALERTS_TOPIC_ARN` environment variable). `osc-iam-admin-<env>` and
`osc-iam-member-<env>` also import `osc-sns-admin-alerts-arn-<env>`.
CloudFormation blocks deletion of any stack whose exports are in use.

If you are doing a full teardown (lambda, iam, and sns), the correct order is:

```text
Destroy order:   lambda → iam-kiosk → iam-admin → iam-member → sns   (most-dependent first)
Rebuild order:   sns/iam (via deploy-base) → lambda
```

If you only need to destroy Lambda or IAM-kiosk, SNS does not need to be touched.
If you need to destroy SNS, **all** stacks that import its exports must be deleted
first (`osc-lambda-<env>`, `osc-iam-admin-<env>`, and `osc-iam-member-<env>`),
even if those stacks are not themselves being rebuilt from scratch.

---

## Step 1 — Destroy the target stack(s)

Each target blocks until CloudFormation confirms the stack is fully deleted before returning.

**Lambda only:**

```bash
make destroy-lambda ENV=dev
```

**IAM only** (only safe after Lambda is already deleted or if Lambda stack does not exist):

```bash
make destroy-iam-kiosk ENV=dev
```

**SNS only:**

```bash
make destroy-sns ENV=dev
```

**All stacks** (in dependency order):

```bash
make destroy-lambda ENV=dev
make destroy-iam-kiosk ENV=dev

# iam-admin and iam-member have no Makefile targets — delete manually:
aws cloudformation delete-stack \
  --stack-name osc-iam-admin-dev \
  --profile outdoorsportsclub --region us-east-1
aws cloudformation wait stack-delete-complete \
  --stack-name osc-iam-admin-dev \
  --profile outdoorsportsclub --region us-east-1

aws cloudformation delete-stack \
  --stack-name osc-iam-member-dev \
  --profile outdoorsportsclub --region us-east-1
aws cloudformation wait stack-delete-complete \
  --stack-name osc-iam-member-dev \
  --profile outdoorsportsclub --region us-east-1

make destroy-sns ENV=dev
```

> If `destroy-iam-kiosk` fails with a `DELETE_FAILED` error and CloudFormation reports that
> `osc-lambda-<env>` still references the role, destroy Lambda first.

---

## Step 2 — Rebuild

**Rebuild SNS and IAM** (both are part of `deploy-base`):

```bash
make deploy-base ENV=dev
```

`deploy-base` is idempotent and safe to run even if only one of the two stacks was
destroyed — it will skip stacks that are already up to date.

**Rebuild Lambda:**

Lambda reads its ZIP artifacts directly from the S3 artifacts bucket. If the ZIPs are
not present in S3 (e.g. after a fresh checkout or on a new machine), `deploy-lambda`
will fail with a key-not-found error. Package and upload them first:

```bash
make package ENV=dev
make upload ENV=dev
```

Then deploy:

```bash
make deploy-lambda ENV=dev
```

Lambda requires the `osc-iam-kiosk-<env>` stack to exist before it can be deployed.
If you destroyed IAM, run `deploy-base` before `deploy-lambda`.

---

## Step 3 — Smoke test

Invoke a function directly to confirm the rebuilt stack is wired correctly:

```bash
make invoke ENV=dev \
  FUNCTION=osc-kiosk-range-lanes-dev \
  PAYLOAD='{"headers":{"x-device-token":"<token>"},"httpMethod":"GET","path":"/v1/kiosk/range/lanes"}'
```

Expected: HTTP 200 with a JSON body. A 401 or 403 indicates the kiosk device
token is missing or invalid and the handler's device-token authorization logic
is rejecting the request; IAM permission issues typically surface as a
`FunctionError` or an unhandled exception in the invocation response.

---

## Troubleshooting

**`DELETE_FAILED` — resource cannot be deleted**
CloudFormation sometimes fails to delete API Gateway stages or Lambda ENIs
immediately. Wait 2–3 minutes and retry `make destroy-lambda ENV=dev`.

**`make destroy-iam-kiosk` fails with export reference error**
`osc-lambda-<env>` imports `osc-iam-kiosk-<env>` exports. Destroy Lambda first.

**`make deploy-lambda` fails with "role does not exist"**
`osc-iam-kiosk-<env>` was destroyed and not yet rebuilt. Run `make deploy-base ENV=dev` first.

**Stack in `ROLLBACK_COMPLETE` state — cannot update**
A failed deploy (not a destroy) can leave a stack in `ROLLBACK_COMPLETE`. CloudFormation
will refuse all subsequent `deploy` attempts with "is in ROLLBACK_COMPLETE state and
cannot be updated". Delete the stack manually and redeploy:

```bash
aws cloudformation delete-stack \
  --stack-name <stack-name> \
  --profile outdoorsportsclub --region us-east-1
aws cloudformation wait stack-delete-complete \
  --stack-name <stack-name> \
  --profile outdoorsportsclub --region us-east-1
```

Then re-run the relevant deploy target. Stacks most likely to reach this state are
`osc-iam-admin-<env>` and `osc-iam-member-<env>`, which fail when `osc-cognito-<env>`
is missing — if their initial deploy attempt fails before the Cognito stack exists,
they land in `ROLLBACK_COMPLETE` and must be deleted before `deploy-base` can succeed.
Ensure `make deploy-cognito ENV=dev` has been run before retrying.
