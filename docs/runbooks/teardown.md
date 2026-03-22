# Teardown Runbook — Outdoor Sports Club (dev)

Complete shutdown procedure for the `dev` environment. This permanently destroys all
data and infrastructure. There is no undo.

**Time budget:** approximately 20 minutes of active work, plus a mandatory 7-day wait
for KMS key deletion.

---

## Prerequisites

* AWS CLI configured with profile `outdoorsportsclub`
* `gh` CLI authenticated
* Venv activated: `source .venv/bin/activate`

---

## Step 1 — Empty S3 buckets

**Why first:** CloudFormation cannot delete a non-empty bucket, and the stacks have
`DeletionPolicy: Retain`, so the buckets will not be deleted by the stack teardown at all.
You must empty them manually.

First, resolve the account ID used in the bucket names:

```bash
ACCOUNT_ID=$(aws sts get-caller-identity \
  --query Account --output text --profile outdoorsportsclub)
```

**Artifacts bucket** — no Object Lock, a simple recursive delete is sufficient:

```bash
aws s3 rm "s3://osc-lambda-artifacts-dev-${ACCOUNT_ID}" \
  --recursive --profile outdoorsportsclub
```

**Waivers bucket** — has S3 Object Lock with versioning enabled. A simple
`s3 rm --recursive` only inserts delete markers; noncurrent versions remain and will
prevent `s3 rb` from succeeding. You must explicitly delete all versions and delete
markers.

The dev bucket uses **Governance mode** with a **7-day** retention window. Governance
locks can be bypassed by any caller with `s3:BypassGovernanceRetention` — pass
`--bypass-governance-retention` to override objects still within the window.

```bash
export WAIVERS_BUCKET="osc-waivers-dev-${ACCOUNT_ID}"

python3 << 'PYEOF'
import json, subprocess, os

bucket  = os.environ["WAIVERS_BUCKET"]
profile = "outdoorsportsclub"

for query, bypass in [
    ("Versions[].{Key:Key,VersionId:VersionId}", True),
    ("DeleteMarkers[].{Key:Key,VersionId:VersionId}", False),
]:
    result = subprocess.run(
        ["aws", "s3api", "list-object-versions",
         "--bucket", bucket,
         "--query", query,
         "--output", "json",
         "--profile", profile],
        capture_output=True, text=True, check=True,
    )
    objs = json.loads(result.stdout) or []
    if not objs:
        print(f"No items matched: {query}")
        continue
    cmd = [
        "aws", "s3api", "delete-objects",
        "--bucket", bucket,
        "--delete", json.dumps({"Objects": objs}),
        "--profile", profile,
    ]
    if bypass:
        cmd.append("--bypass-governance-retention")
    subprocess.run(cmd, check=True)
    print(f"Deleted {len(objs)} item(s)")
PYEOF
```

Then delete both buckets:

```bash
aws s3 rb "s3://osc-waivers-dev-${ACCOUNT_ID}" --profile outdoorsportsclub
aws s3 rb "s3://osc-lambda-artifacts-dev-${ACCOUNT_ID}" --profile outdoorsportsclub
```

---

## Step 2 — Delete AWS Backup recovery points and vault

The backup vault cannot be deleted while it contains recovery points.

```bash
# List recovery points
aws backup list-recovery-points-by-backup-vault \
  --backup-vault-name osc-backup-vault-dev \
  --profile outdoorsportsclub --region us-east-1 \
  --query 'RecoveryPoints[*].RecoveryPointArn' --output text

# Delete each one (repeat for every ARN returned above)
aws backup delete-recovery-point \
  --backup-vault-name osc-backup-vault-dev \
  --recovery-point-arn <ARN> \
  --profile outdoorsportsclub --region us-east-1
```

Or delete all recovery points in a loop:

```bash
aws backup list-recovery-points-by-backup-vault \
  --backup-vault-name osc-backup-vault-dev \
  --profile outdoorsportsclub --region us-east-1 \
  --query 'RecoveryPoints[*].RecoveryPointArn' --output text \
| tr '\t' '\n' \
| while read ARN; do
    aws backup delete-recovery-point \
      --backup-vault-name osc-backup-vault-dev \
      --recovery-point-arn "$ARN" \
      --profile outdoorsportsclub --region us-east-1
  done
```

Then delete the vault:

```bash
aws backup delete-backup-vault \
  --backup-vault-name osc-backup-vault-dev \
  --profile outdoorsportsclub --region us-east-1
```

---

## Step 3 — Delete Aurora cluster (retained resource)

The Aurora cluster has `DeletionPolicy: Retain` and will not be removed by stack
deletion. This runbook always deletes without a final snapshot. If you need to preserve
data, take a manual snapshot via the AWS console before running these commands.

```bash
# Delete the cluster instance first
aws rds delete-db-instance \
  --db-instance-identifier osc-aurora-dev-instance \
  --skip-final-snapshot \
  --profile outdoorsportsclub --region us-east-1

# Wait for the instance to finish deleting, then delete the cluster
aws rds wait db-instance-deleted \
  --db-instance-identifier osc-aurora-dev-instance \
  --profile outdoorsportsclub --region us-east-1

aws rds delete-db-cluster \
  --db-cluster-identifier osc-aurora-dev \
  --skip-final-snapshot \
  --profile outdoorsportsclub --region us-east-1
```

If the instance identifier differs, look it up first:

```bash
aws rds describe-db-clusters \
  --db-cluster-identifier osc-aurora-dev \
  --profile outdoorsportsclub --region us-east-1 \
  --query 'DBClusters[0].DBClusterMembers[*].DBInstanceIdentifier' \
  --output text
```

---

## Step 4 — Delete Cognito user pool (retained resource)

The Cognito user pool has `DeletionPolicy: Retain`. Delete it manually using a dynamic
lookup to avoid hardcoding the pool ID across recreations.

```bash
USER_POOL_ID=$(aws cognito-idp list-user-pools \
  --max-results 60 \
  --profile outdoorsportsclub --region us-east-1 \
  --query "UserPools[?Name=='osc-users-dev'].Id" \
  --output text)

aws cognito-idp delete-user-pool \
  --user-pool-id "$USER_POOL_ID" \
  --profile outdoorsportsclub --region us-east-1
```

---

## Step 5 — Schedule KMS key deletion (7-day mandatory minimum)

KMS keys cannot be deleted immediately. AWS enforces a minimum 7-day waiting period.
Schedule both keys for deletion now — they will be deleted automatically after the
waiting period.

```bash
aws kms schedule-key-deletion \
  --key-id alias/osc-aurora-dev \
  --pending-window-in-days 7 \
  --profile outdoorsportsclub --region us-east-1

aws kms schedule-key-deletion \
  --key-id alias/osc-s3-waivers-dev \
  --pending-window-in-days 7 \
  --profile outdoorsportsclub --region us-east-1
```

Note: During the pending window the keys are disabled and cannot be used, but they
continue to accrue the $1/month/key charge until deletion completes.

---

## Step 6 — Delete CloudFormation stacks

Delete in reverse-dependency order. IAM stacks must be deleted before Cognito because
the admin IAM stack imports the Cognito user pool ARN as a CloudFormation export —
deleting Cognito first causes `DELETE_FAILED` on the IAM stacks. Wait for each stack
to reach `DELETE_COMPLETE` before proceeding.

```bash
ENV=dev
PROFILE=outdoorsportsclub
REGION=us-east-1

for STACK in \
  osc-lambda \
  osc-api \
  osc-iam-member \
  osc-iam-admin \
  osc-iam-kiosk \
  osc-backup \
  osc-cognito \
  osc-sns \
  osc-aurora \
  osc-s3 \
  osc-secrets \
  osc-artifacts \
  osc-kms; do
    echo "Deleting ${STACK}-${ENV}..."
    aws cloudformation delete-stack \
      --stack-name "${STACK}-${ENV}" \
      --profile "$PROFILE" --region "$REGION"
    aws cloudformation wait stack-delete-complete \
      --stack-name "${STACK}-${ENV}" \
      --profile "$PROFILE" --region "$REGION"
    echo "${STACK}-${ENV} deleted."
  done
```

If a stack deletion fails because a retained resource still exists (e.g., the Aurora
cluster or Cognito user pool was not yet fully deleted), re-run that stack's deletion
after the resource finishes deleting.

---

## Step 7 — Delete Amplify app

```bash
AMPLIFY_APP_ID=$(aws amplify list-apps \
  --profile outdoorsportsclub --region us-east-1 \
  --query "apps[?name=='outdoorsportsclub'].appId" \
  --output text)

aws amplify delete-app \
  --app-id "$AMPLIFY_APP_ID" \
  --profile outdoorsportsclub --region us-east-1
```

---

## Step 8 — Delete Google OAuth client (if configured)

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials
2. Find the OAuth 2.0 client for Outdoor Sports Club
3. Delete it

---

## Verification — confirm nothing is still running

```bash
aws cloudformation list-stacks \
  --profile outdoorsportsclub --region us-east-1 \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
  --query 'StackSummaries[?contains(StackName, `osc`)].StackName'

aws s3 ls --profile outdoorsportsclub | grep osc

aws rds describe-db-clusters \
  --profile outdoorsportsclub --region us-east-1 \
  --query 'DBClusters[?DBClusterIdentifier==`osc-aurora-dev`].DBClusterIdentifier'

aws cognito-idp list-user-pools \
  --max-results 20 \
  --profile outdoorsportsclub --region us-east-1 \
  --query 'UserPools[?contains(Name, `osc`)].Name'
```

---

## Optional — Delete GitHub repository

This step is separate from the main teardown because it is irreversible and independent
of the AWS resources above. Do this only if you intend to fully decommission the project.

Make a local archive first if you want to keep the code:

```bash
git clone --mirror https://github.com/vrwmiller/outdoorsportsclub.git outdoorsportsclub-archive.git
```

Then delete the repository:

```bash
gh repo delete vrwmiller/outdoorsportsclub --yes
```

All four commands should return empty results.

---

## Cost note

After completing steps 1–7 the primary recurring charges stop immediately. The two KMS
keys continue at $1/month each until the 7-day deletion window expires.
