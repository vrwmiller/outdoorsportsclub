# CI / Deployment Pipeline Failure

> **BLOCKED RUNBOOK** — This runbook cannot be completed until `deploy-dev.yml` and `deploy-prod.yml` workflow files are authored. Until then, the **Webmaster** is the escalation point for all pipeline failures.

**Audience:** Webmaster / developer with repository and AWS access

This runbook covers diagnosing and recovering from a failed GitHub Actions deployment run for the Outdoor Sports Club project.

---

## Prerequisites

* Repository Admin or Webmaster access to GitHub Actions
* AWS CLI configured with the `outdoorsportsclub` profile (`us-east-1`)
* Read access to **AWS CloudFormation**, **Aurora**, and **Lambda** in the AWS console

---

## Step 1 — Identify the failed step

1. Open the failed workflow run in GitHub Actions
2. Expand the failed job and identify which of the three deployment steps failed:
   * **Step 1** — `cloudformation deploy` (infrastructure change)
   * **Step 2** — migration loop (RDS Data API SQL execution)
   * **Step 3** — `lambda update-function-code` (Lambda package upload)

> A failure in step 2 or 3 means step 1 (CloudFormation) succeeded. Infrastructure changes are already live; code and/or data are not yet updated.

---

## Step 2 — Assess the failure

<!-- To be completed when workflow files are authored. Expected content: -->
<!-- - CloudFormation stack status check commands -->
<!-- - Aurora migration rollback / idempotency verification -->
<!-- - Lambda version rollback procedure -->
<!-- - GitHub Actions re-run vs. git revert guidance -->

> Procedure to be written when deployment workflow files are authored.

---

## Escalation

Until this runbook is complete, contact the **Webmaster** immediately on any pipeline failure. Do not re-trigger the workflow without first understanding which step failed and why.
