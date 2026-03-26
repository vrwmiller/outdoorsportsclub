# Secrets Rotation

**Audience:** Webmaster (Level 6).

This runbook covers rotating the secrets stored in **AWS Secrets Manager** for the Outdoor Sports Club system: the Stripe API key, the Aurora database credentials, and the kiosk device-token HMAC salt. Each secret lives in the environment-specific namespace (`osc/dev/…` for dev, `osc/prod/…` for prod).

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

* Most Lambda functions read secrets from **AWS Secrets Manager** at cold start and cache them in memory for the lifetime of the container — there are no cached copies in environment variables. For those handlers, a rotated secret takes effect on the next cold start. Some handlers (for example, the kiosk device-provisioning Lambdas described in Part C) refresh specific secrets on a short TTL rather than only at cold start. For urgent rotations, force new containers by redeploying each affected Lambda function through the standard deployment pipeline (`make deploy-lambda`).
* **AWS Secrets Manager** does not send a notification when a manual `put-secret-value` is called. Monitor Lambda error rates in **Amazon CloudWatch** for the 10 minutes following any rotation.
* **Rotation must be applied to the primary region first**, then confirmed in replica regions before the old credential is revoked or the old secret is deleted. Reverting the order can leave replica regions with invalid secrets.

---

## Part C — Rotate the kiosk device-token HMAC salt

> **Warning:** The salt is cached at Lambda cold-start. After updating the secret, **all kiosk Lambda containers must be force-cold-started** before the new salt takes effect. Until that step is complete, tokens generated by the kiosk provisioning flow (which uses the new salt) will be rejected by warm Lambda containers still holding the old salt — kiosk sign-in will be broken for those containers. Complete Steps 1–4 in sequence without interruption.

### 1. Generate a new salt

Generate a cryptographically random 32-byte (256-bit) salt represented as 64 hex characters:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
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

> **CloudFormation parameter note:** The secrets stack (`infra/stacks/secrets.yaml`) provisions this secret from the `DeviceTokenSalt` CloudFormation parameter at deploy time. After rotating the secret here, also update the stored/recorded deploy-time parameter value for this stack (e.g., in your deployment notes or secrets vault). If the stack is redeployed without updating the parameter, CloudFormation will overwrite the rotated secret back to the old salt value.

### 3. Wait for multi-region replication (prod only)

Verify the updated secret has propagated to all replica regions before force-cold-starting Lambdas (see Step 3 in Part A for the verification command, substituting the `device-token-salt` secret name).

### 4. Force a cold start on all kiosk Lambda functions

The device-token salt is fetched once at Lambda cold-start and cached for the lifetime of the container. Warm containers will continue using the old salt after the secret is updated. Force all containers to recycle by updating a dummy environment variable on each kiosk Lambda:

```bash
ROTATED_AT=$(date -u +%Y%m%dT%H%M%SZ)
for FUNC in \
  osc-kiosk-checkin-prod \
  osc-kiosk-checkout-prod \
  osc-kiosk-dues-prod \
  osc-kiosk-waiver-prod \
  osc-kiosk-guest-payment-prod \
  osc-kiosk-consumable-purchase-prod \
  osc-kiosk-waitlist-cancel-prod \
  osc-kiosk-range-lanes-prod; do
  CURRENT=$(aws lambda get-function-configuration \
    --function-name "$FUNC" \
    --profile outdoorsportsclub \
    --query 'Environment.Variables' --output json)
  MERGED=$(echo "$CURRENT" | python3 -c \
    "import json,sys; d=json.load(sys.stdin); d['SALT_ROTATED_AT']='$ROTATED_AT'; print(json.dumps(d))")
  ENV_JSON="{\"Variables\":$MERGED}"
  aws lambda update-function-configuration \
    --function-name "$FUNC" \
    --environment "$ENV_JSON" \
    --profile outdoorsportsclub
  aws lambda wait function-updated --function-name "$FUNC" --profile outdoorsportsclub
  echo "Updated $FUNC"
done
```

Replace `-prod` with `-dev` for dev. The loop reads the current `Environment.Variables` map for each function before writing, so no existing environment variables are overwritten.

### 5. Wait for provisioning Lambdas to pick up the new salt

The kiosk device-provisioning functions (`osc-admin-devices-pairing-code-*` and `osc-devices-pair-*`) refresh the HMAC salt from Secrets Manager every 60 seconds rather than caching it for the lifetime of the container. Wait at least 60 seconds after Step 2 before proceeding, so any warm provisioning containers have refreshed to the new salt. Tokens signed before this window may use the old salt and will be rejected by kiosk handlers.

### 6. Re-provision kiosk devices

All device tokens were signed with the old salt. After the 60-second wait, the new salt is active in all containers and all existing tokens are invalid. Re-provision each physical kiosk device through the admin provisioning flow to generate new tokens signed with the new salt.

### 7. Verify

1. Using a newly provisioned device token and a known-good member badge (active dues, correct training level, range open), perform a check-in scan at each kiosk — a `200` confirms both the new device token and the new salt are accepted. Repeat for every physical kiosk.
2. Using the same device token, trigger a quick call to each of the other kiosk routes (checkout, dues, waiver, guest-payment, consumable-purchase, waitlist-cancel, range-lanes) to confirm each of the eight Lambda functions recycled successfully. A `200` or expected business-logic response (e.g., `404 Not Found` for a non-existent lane) is acceptable; a `403` with response body `{"error":"Forbidden"}` means that specific function's container did not cold-start with the new salt — re-run Step 4 for that function alone and retest.
3. For the first 10 minutes after rotation, monitor the kiosk Lambda **Amazon CloudWatch Logs** for unexpected spikes in `403` responses; sustained `403` responses for newly-provisioned device tokens indicate a missed cold start.
