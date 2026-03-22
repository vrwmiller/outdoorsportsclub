# Teardown Runbook — Outdoor Sports Club (dev)

Complete shutdown procedure for the `dev` environment. This permanently destroys all
data and infrastructure. There is no undo.

**Time budget:** approximately 20 minutes of active work, plus a mandatory 7-day wait
for KMS key deletion.

---

## Prerequisites

- AWS CLI configured with profile `outdoorsportsclub`
- `gh` CLI authenticated
- Venv activated: `source .venv/bin/activate`

---

## Step 1 — Empty S3 buckets

**Why first:** CloudFormation cannot delete a non-empty bucket, and the stacks have
`DeletionPolicy: Retain`, so the buckets will not be deleted by the stack teardown at all.
You must empty them manually.

```bash
aws s3 rm s3://osc-waivers-dev-920835814440 --recursive --profile outdoorsportsclub
aws s3 rm s3://osc-lambda-artifacts-dev-920835814440 --recursive --profile outdoorsportsclub
```

If S3 Object Lock is enabled on `osc-waivers-dev-*` (it will be once waivers are in use),
objects under a Compliance-mode lock cannot be deleted until the retention period expires
(7 years). You would need to contact AWS Support to override this, or simply accept that
the bucket will persist until the lock expires.

Then delete the buckets:

```bash
aws s3 rb s3://osc-waivers-dev-920835814440 --profile outdoorsportsclub
aws s3 rb s3://osc-lambda-artifacts-dev-920835814440 --profile outdoorsportsclub
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

The Aurora cluster has `DeletionPolicy: Retain` and will not be removed by the stack
deletion. Delete it manually. Skip the final snapshot if you do not need the data.

```bash
# Delete the cluster instances first
aws rds describe-db-clusters \
  --profile outdoorsportsclub --region us-east-1 \
  --query 'DBClusters[?contains(DBClusterIdentifier, `osc`)].DBClusterMembers[*].DBInstanceIdentifier' \
  --output text \
| tr '\t' '\n' \
| while read INSTANCE; do
    aws rds delete-db-instance \
      --db-instance-identifier "$INSTANCE" \
      --skip-final-snapshot \
      --profile outdoorsportsclub --region us-east-1
  done

# Then delete the cluster (wait for instances to finish deleting first)
aws rds describe-db-clusters \
  --profile outdoorsportsclub --region us-east-1 \
  --query 'DBClusters[?contains(DBClusterIdentifier, `osc`)].DBClusterIdentifier' \
  --output text \
| tr '\t' '\n' \
| while read CLUSTER; do
    aws rds delete-db-cluster \
      --db-cluster-identifier "$CLUSTER" \
      --skip-final-snapshot \
      --profile outdoorsportsclub --region us-east-1
  done
```

---

## Step 4 — Delete Cognito user pool (retained resource)

The Cognito user pool has `DeletionPolicy: Retain`. Delete it manually.

```bash
aws cognito-idp delete-user-pool \
  --user-pool-id us-east-1_XaJgi6tid \
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

Delete in reverse-dependency order. Wait for each to reach `DELETE_COMPLETE` before
proceeding.

```bash
ENV=dev
PROFILE=outdoorsportsclub
REGION=us-east-1

for STACK in \
  osc-lambda-dev \
  osc-api-dev \
  osc-backup-dev \
  osc-aurora-dev \
  osc-s3-dev \
  osc-cognito-dev \
  osc-sns-dev \
  osc-secrets-dev \
  osc-iam-member-dev \
  osc-iam-admin-dev \
  osc-iam-kiosk-dev \
  osc-artifacts-dev \
  osc-kms-dev; do
    echo "Deleting $STACK..."
    aws cloudformation delete-stack \
      --stack-name "$STACK" \
      --profile "$PROFILE" --region "$REGION"
    aws cloudformation wait stack-delete-complete \
      --stack-name "$STACK" \
      --profile "$PROFILE" --region "$REGION"
    echo "$STACK deleted."
  done
```

If a stack deletion fails because a retained resource still exists (e.g., the Aurora
cluster or Cognito user pool was not yet fully deleted), re-run that stack's deletion
after the resource finishes deleting.

---

## Step 7 — Delete Amplify app

```bash
aws amplify delete-app \
  --app-id d2rljf3gefhatr \
  --profile outdoorsportsclub --region us-east-1
```

---

## Step 8 — Delete Google OAuth client (if configured)

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials
2. Find the OAuth 2.0 client for Outdoor Sports Club
3. Delete it

---

## Step 9 — Delete GitHub repository

```bash
gh repo delete vrwmiller/outdoorsportsclub --yes
```

This is irreversible. Make a local archive first if you want to keep the code:

```bash
git clone --mirror https://github.com/vrwmiller/outdoorsportsclub.git outdoorsportsclub-archive.git
```

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
  --query 'DBClusters[?contains(DBClusterIdentifier, `osc`)].DBClusterIdentifier'

aws cognito-idp list-user-pools \
  --max-results 20 \
  --profile outdoorsportsclub --region us-east-1 \
  --query 'UserPools[?contains(Name, `osc`)].Name'
```

All four commands should return empty results.

---

## Cost note

After completing steps 1–7 the primary recurring charges stop immediately. The two KMS
keys continue at $1/month each until the 7-day deletion window expires.
