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
| `osc/prod/device-token-salt` | HMAC-SHA256 salt used to sign kiosk device tokens | Suspected kiosk device compromise, token forgery, or routine rotation |
| `osc/dev/device-token-salt` | HMAC-SHA256 salt (dev) | Suspected compromise or routine rotation |

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

---

## Part C — Rotate the kiosk device-token HMAC salt

> **Warning:** The salt is cached at Lambda cold-start. After updating the secret, **all kiosk Lambda containers must be force-cold-started** before the new salt takes effect. Until that step is complete, tokens generated by the kiosk provisioning flow (which uses the new salt) will be rejected by warm Lambda containers still holding the old salt — kiosk sign-in will be broken for those containers. Complete Steps 1–4 in sequence without interruption.

### 1. Generate a new salt

Generate a cryptographically random 32-byte value and base64-encode it:

```bash
python3 -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

Copy the output — it is the new salt value.

### 2. Update the secret in AWS Secrets Manager

The secret must be a JSON object with a `salt` key:

```bash
aws secretsmanager put-secret-value \
  --secret-id osc/prod/device-token-salt \
  --secret-string '{"salt":"<new_salt_value>"}' \
  --profile outdoorsportsclub
```

Replace `osc/prod/device-token-salt` with `osc/dev/device-token-salt` for dev.

### 3. Wait for multi-region replication (prod only)

Verify the updated secret has propagated to all replica regions before force-cold-starting Lambdas (see Step 3 in Part A for the verification command, substituting the `device-token-salt` secret name).

### 4. Force a cold start on all kiosk Lambda functions

The device-token salt is fetched once at Lambda cold-start and cached for the lifetime of the container. Warm containers will continue using the old salt after the secret is updated. Force all containers to recycle by updating a dummy environment variable on each kiosk Lambda:

```bash
for FUNC in \
  osc-prod-kiosk-checkin \
  osc-prod-kiosk-checkout \
  osc-prod-kiosk-dues \
  osc-prod-kiosk-waiver \
  osc-prod-kiosk-guest-payment \
  osc-prod-kiosk-consumable-purchase \
  osc-prod-kiosk-waitlist-cancel \
  osc-prod-kiosk-range-lanes; do
  aws lambda update-function-configuration \
    --function-name "$FUNC" \
    --environment "Variables={SALT_ROTATED_AT=$(date -u +%Y%m%dT%H%M%SZ)}" \
    --profile outdoorsportsclub
  echo "Updated $FUNC"
done
```

Replace `osc-prod-` with `osc-dev-` for dev. Wait for each update to reach `LastUpdateStatus: Successful` before proceeding to the next, or loop with a `aws lambda wait function-updated` call.

> **Note:** This command replaces the entire `Environment.Variables` map. If any kiosk Lambda already has environment variables set beyond what this command includes (e.g., `S3_WAIVER_BUCKET`, `SNS_ALERTS_TOPIC_ARN`), retrieve the current map first and merge the new key:
>
> ```bash
> CURRENT=$(aws lambda get-function-configuration \
>   --function-name osc-prod-kiosk-waiver \
>   --profile outdoorsportsclub \
>   --query 'Environment.Variables' --output json)
> MERGED=$(echo "$CURRENT" | python3 -c \
>   "import json,sys; d=json.load(sys.stdin); d['SALT_ROTATED_AT']='$(date -u +%Y%m%dT%H%M%SZ)'; print(json.dumps(d))")
> aws lambda update-function-configuration \
>   --function-name osc-prod-kiosk-waiver \
>   --environment "Variables=$MERGED" \
>   --profile outdoorsportsclub
> ```

### 5. Re-provision kiosk devices

All device tokens were signed with the old salt. After the cold start, the new salt is active and all existing tokens are invalid. Re-provision each physical kiosk device through the admin provisioning flow to generate new tokens signed with the new salt.

### 6. Verify

1. Attempt a check-in scan at each kiosk — a `200` confirms the new token is accepted.
2. Monitor **Amazon CloudWatch Logs** for `403` responses with `error: PermissionError` in the kiosk Lambda log groups for the 10 minutes following rotation. Any `403` after re-provisioning indicates a container that did not cold-start — re-run Step 4 for that specific function.
