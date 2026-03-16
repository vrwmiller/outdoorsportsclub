# AWS Account Setup

**Audience:** Webmaster / developer setting up a new local environment for the Outdoor Sports Club project.

This runbook covers creating a dedicated IAM user, attaching the required permissions policy, enabling MFA, generating an access key, and configuring the AWS CLI with a named profile.

---

## Prerequisites

* An AWS account (root account access required for first-time setup)
* AWS CLI v2 installed locally — verify with:

  ```bash
  aws --version
  ```

  Install from: <https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html>

---

## 1. Create a dedicated IAM user

Do not use your root account or reuse a user from another project.

1. Sign in to the AWS console as root (or an existing admin user)
2. Navigate to **IAM → Users → Create user**
3. Set username to something descriptive (e.g. `outdoorsportsclub-dev`)
4. Select **Provide user access to the AWS Management Console** if you want console access (recommended for debugging and monitoring)
5. Complete the user creation wizard

---

## 2. Attach AdministratorAccess

1. Open the new user → **Permissions** tab → **Add permissions**
2. Choose **Attach policies directly**
3. Search for `AdministratorAccess`, check it, click **Next** → **Add permissions**

> This broad permission is appropriate for the developer/Webmaster role during active development. Runtime service roles defined in CloudFormation use least-privilege policies scoped to only what each service needs.

---

## 3. Enable MFA

Required before using the account — this account will hold member PII, payment credentials (Stripe), and legal waiver storage (S3).

1. Open the user → **Security credentials** tab → **Assign MFA device**
2. Choose **Authenticator app**
3. Scan the QR code with your authenticator app (e.g. 1Password, Authy, Google Authenticator)
4. Enter two consecutive TOTP codes to confirm

Also enable MFA on the **root account** if not already done: root account → top-right menu → **Security credentials**.

---

## 4. Create an access key

1. Open the user → **Security credentials** tab → **Create access key**
2. Select **Command Line Interface (CLI)** as the use case
3. Acknowledge the recommendation and click **Next**
4. Copy the **Access key ID** and **Secret access key** — the secret is shown only once

Store these securely (e.g. in a password manager). Do not commit them to the repository.

---

## 5. Configure the AWS CLI

Use a named profile to keep this project's credentials separate from any other AWS accounts on your machine:

```bash
aws configure --profile outdoorsportsclub
```

Enter the following when prompted:

| Prompt | Value |
| :--- | :--- |
| AWS Access Key ID | your access key ID |
| AWS Secret Access Key | your secret access key |
| Default region name | `us-east-1` (or your chosen region — must match the region used for all CloudFormation stacks) |
| Default output format | `json` |

---

## 6. Verify

```bash
aws sts get-caller-identity --profile outdoorsportsclub
```

Expected output:

```json
{
    "UserId": "AIDA...",
    "Account": "123456789012",
    "Arn": "arn:aws:iam::123456789012:user/outdoorsportsclub-dev"
}
```

If this returns your user's ARN, the profile is configured correctly and ready to use.

---

## Using the profile

All AWS CLI commands for this project must use `--profile outdoorsportsclub`:

```bash
aws s3 ls --profile outdoorsportsclub
aws cloudformation deploy ... --profile outdoorsportsclub
```

Or set it for the duration of a terminal session:

```bash
export AWS_PROFILE=outdoorsportsclub
```

The Amplify Gen 2 CLI respects the `AWS_PROFILE` environment variable when deploying.
