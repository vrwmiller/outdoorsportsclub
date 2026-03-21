# Secrets Rotation

**Audience:** Webmaster (Level 6).

This runbook covers rotating the secrets stored in **AWS Secrets Manager** for the Outdoor Sports Club system: the Stripe API key and the Aurora database credentials. Each secret lives in the environment-specific namespace (`osc/dev/…` for dev, `osc/prod/…` for prod).

> Always rotate `dev` and `prod` secrets independently. Never copy a secret from one environment to the other.

See `docs/design.md` Section 8 (multi-region replication) for the replication order requirement.

---

## Secret inventory

| Secret name | Description | Rotation trigger |
| :--- | :--- | :--- |
| `osc/prod/stripe-key` | Stripe live-mode secret key | Stripe key compromise, routine annual rotation, or staff change |
| `osc/dev/stripe-key` | Stripe test-mode secret key | Stripe key compromise or routine rotation |
| `osc/prod/db-credentials` | Aurora master credentials (`username` / `password`) | Credential compromise, routine rotation, or access policy change |
| `osc/dev/db-credentials` | Aurora dev master credentials | Credential compromise or routine rotation |

---

## Part A — Rotate the Stripe API key

### 1. Generate a new key in Stripe

1. Sign in to the [Stripe Dashboard](https://dashboard.stripe.com)
   * For **prod**: use the **Live mode** toggle (top-left)
   * For **dev**: use **Test mode**
2. Navigate to **Developers → API keys**
3. Click **Create secret key** (or **Roll key** on the existing restricted key)
4. Copy the new secret key — it is shown only once

### 2. Update the secret in AWS Secrets Manager

```bash
aws secretsmanager put-secret-value \
  --secret-id osc/prod/stripe-key \
  --secret-string 'sk_live_XXXXXXXXXXXX' \
  --profile outdoorsportsclub
```

Replace `osc/prod/stripe-key` with `osc/dev/stripe-key` for dev. Replace `sk_live_XXXXXXXXXXXX` with the key value copied from Stripe.

### 3. Wait for multi-region replication (prod only)

If the prod stack has multi-region replication enabled, the update must propagate to all replica regions before traffic shifts. Wait approximately 30 seconds, then verify the replica:

```bash
aws secretsmanager get-secret-value \
  --secret-id osc/prod/stripe-key \
  --region us-east-2 \
  --profile outdoorsportsclub
```

Confirm the `SecretString` contains the new key value. Do not revoke the old Stripe key until replication is confirmed.

### 4. Revoke the old Stripe key

Once the new key is confirmed in all regions (and in `dev` if both were rotated):

1. Return to the Stripe Dashboard
2. Navigate to **Developers → API keys**
3. Delete or revoke the old key

### 5. Verify

Trigger a test transaction (test mode) or monitor **Amazon CloudWatch Alarm** for Lambda errors after the rotation. A `401` from Stripe indicates a Lambda is still using the old key — check for any cached secret values in Lambda environment variables (none should exist; the design reads secrets from **AWS Secrets Manager** at runtime).

---

## Part B — Rotate Aurora database credentials

> **Warning:** Incorrect credentials will make the database inaccessible to all Lambda functions. Prepare during a low-traffic window. Have the Aurora console open in a separate browser tab before proceeding.

### 1. Generate new credentials

Choose a strong, randomly generated password. Store it temporarily in a password manager — do not write it to disk or put it in the repository.

### 2. Update the Aurora master password

1. Open the **AWS console → RDS → Databases**
2. Select the Aurora cluster for the target environment
3. Click **Modify**
4. Under **Settings**, enter the new master password
5. Click **Continue** → select **Apply immediately** → **Modify cluster**

Aurora applies the change immediately. The cluster remains online during the change.

### 3. Update the secret in AWS Secrets Manager

```bash
aws secretsmanager put-secret-value \
  --secret-id osc/prod/db-credentials \
  --secret-string '{"username":"<db_user>","password":"<new_password>","host":"<cluster_endpoint>","dbname":"<db_name>"}' \
  --profile outdoorsportsclub
```

> The `host`, `dbname`, and `username` fields do not change on a password rotation — copy them from the existing secret. To view the current secret value (before rotation):
>
> ```bash
> aws secretsmanager get-secret-value \
>   --secret-id osc/prod/db-credentials \
>   --profile outdoorsportsclub
> ```

### 4. Wait for multi-region replication (prod only)

Verify the updated secret has propagated to replica regions (see Step 3 in Part A for the verification command, substituting the `db-credentials` secret name).

### 5. Verify

Check **Amazon CloudWatch Logs** for Lambda function logs immediately after rotation. Database connection errors (`could not connect to server`, `FATAL: password authentication failed`) indicate a mismatch between the secret and the Aurora master password. Resolve by repeating Steps 2–3 with matching values.

---

## Notes

* Lambda functions read secrets from **AWS Secrets Manager** at cold start — there are no cached copies in environment variables. A rotated secret takes effect on the next Lambda cold start. For urgent rotations, force new containers by redeploying each affected Lambda function (e.g., update the function configuration to publish a new version and force a fresh deployment).
* **AWS Secrets Manager** does not send a notification when a manual `put-secret-value` is called. Monitor Lambda error rates in **Amazon CloudWatch** for the 10 minutes following any rotation.
* **Rotation must be applied to the primary region first**, then confirmed in replica regions before the old credential is revoked or the old secret is deleted. Reverting the order can leave replica regions with invalid secrets.
