# Runbook: Aurora Master Secret Cleanup (ODQ 33)

## Context

PR #55 migrated the Aurora cluster to `ManageMasterUserPassword: true`, causing Aurora to create and manage its own master-user secret. The previously provisioned `AuroraMasterSecret` in `infra/stacks/secrets.yaml` (`osc/<env>/aurora-master`) is now orphaned — no stack exports or Lambda functions reference it.

Because the resource carries `DeletionPolicy: Retain`, simply removing it from the CloudFormation template does not delete the underlying Secrets Manager secret. This runbook covers removing the resource from the template and manually deleting the retained secret.

## Pre-requisites

- AWS CLI configured with the `outdoorsportsclub` profile and sufficient IAM permissions (`cloudformation:*`, `secretsmanager:DeleteSecret`)
- No CloudFormation stack currently imports `osc-aurora-master-secret-arn-<env>`

## Steps

### 1. Verify no remaining imports

```bash
grep -r "osc-aurora-master-secret-arn" infra/
```

Expected result: no output. If any matches appear, do not proceed — investigate which stack imports the export before continuing.

### 2. Remove the resource and output from the template

In `infra/stacks/secrets.yaml`, delete:

- The `AuroraMasterSecret` resource block
- The `AuroraMasterSecretArn` output block (which exports `osc-aurora-master-secret-arn-<env>`)

### 3. Deploy the updated stack

```bash
# dev
make deploy-secrets ENV=dev

# prod (after dev is confirmed clean)
make deploy-secrets ENV=prod
```

Confirm the CloudFormation stack update completes with status `UPDATE_COMPLETE`. The retained Secrets Manager secret is not deleted by this step — that is done manually in Step 4.

### 4. Manually delete the retained secret

```bash
# dev
aws secretsmanager delete-secret \
  --force-delete-without-recovery \
  --secret-id osc/dev/aurora-master \
  --profile outdoorsportsclub

# prod
aws secretsmanager delete-secret \
  --force-delete-without-recovery \
  --secret-id osc/prod/aurora-master \
  --profile outdoorsportsclub
```

`--force-delete-without-recovery` bypasses the default 7–30 day recovery window. Use this only after confirming the secret is genuinely orphaned (Step 1 passed and the stack update in Step 3 succeeded).

### 5. Verify deletion

```bash
aws secretsmanager describe-secret \
  --secret-id osc/dev/aurora-master \
  --profile outdoorsportsclub
```

Expected result: `ResourceNotFoundException`. Repeat for `prod`.

## Notes

- The stale secret contains the former Aurora master password. Aurora rotates the managed-password secret on its own schedule (within 7 days of the PR #55 deploy), so by the time this runbook is executed the old password will no longer be active.
- This runbook is safe to run at any time after the PR #55 deploy, but is classified Post-launch because no active system component depends on the orphaned secret.
