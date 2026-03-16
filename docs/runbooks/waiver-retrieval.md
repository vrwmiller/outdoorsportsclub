# Waiver Retrieval

**Audience:** Administrator (Level 5) or Webmaster (Level 6).

This runbook covers retrieving a signed waiver PDF from **Amazon S3** for a specific member or guest. Waivers are stored with **S3 Object Lock** (Compliance Mode, 7-year retention) and encrypted with **AWS KMS**. They cannot be deleted, but they can be viewed and downloaded by authorized personnel.

See `docs/design.md` Sections 5.5 and 7.2 for the `activity_logs.waiver_s3_key` field and the waiver storage path convention.

---

## Prerequisites

* **Admin Portal** access with a Level 5+ account, **or** AWS console / CLI access for direct S3 retrieval
* The member's name or member number, or the guest's name and phone number, to identify the correct `activity_logs` record

---

## Part A — Retrieve via the Admin Portal (recommended)

1. Sign in to the **Admin Portal** with a Level 5+ account
2. Navigate to **Members** → locate the member → click **Activity log**
3. Filter by `activity_type = Waiver-Signed`
4. Identify the relevant waiver record — note the date and whether it is a member waiver (`guest_id = NULL`) or a guest waiver (`guest_id` populated)
5. Click **Download waiver** — the portal generates a pre-signed S3 URL for the object and opens the PDF in a new tab

For a **guest waiver**, navigate to the guest's record via the member's recent visit history and follow the same steps.

---

## Part B — Retrieve via AWS CLI (if Admin Portal is unavailable)

### Find the S3 key

Query `activity_logs` directly for the most recent `Waiver-Signed` event:

**Member waiver:**

```sql
SELECT waiver_s3_key, timestamp
FROM activity_logs
WHERE member_id = '<member_uuid>'
  AND activity_type = 'Waiver-Signed'
  AND guest_id IS NULL
ORDER BY timestamp DESC
LIMIT 1;
```

**Guest waiver:**

```sql
SELECT waiver_s3_key, timestamp
FROM activity_logs
WHERE guest_id = '<guest_uuid>'
  AND activity_type = 'Waiver-Signed'
ORDER BY timestamp DESC
LIMIT 1;
```

The key follows one of these patterns:

| Waiver type | S3 key pattern |
| :--- | :--- |
| Member | `waivers/<member_id>/<timestamp>.pdf` |
| Guest | `waivers/guests/<guest_id>/<timestamp>.pdf` |

### Download the object

```bash
aws s3 cp "s3://<waiver-bucket-name>/<waiver_s3_key>" ./waiver.pdf \
  --profile outdoorsportsclub
```

Replace `<waiver-bucket-name>` with the correct S3 bucket for the environment (`prod` or `dev`). The bucket name is available in the CloudFormation stack outputs.

> Objects are KMS-encrypted. Your IAM identity must have `kms:Decrypt` permission on the waiver bucket's KMS key to successfully download and open the file. If you receive an `Access Denied` response, confirm your IAM permissions in the **AWS console → IAM → your user → Permissions**.

---

## Notes

* **S3 Object Lock (Compliance Mode)** prevents deletion or overwrite of any waiver object for 7 years from the date of upload. Objects that appear to be missing have not been deleted — they were either never uploaded (check **Amazon CloudWatch Logs** for the Lambda function that handles waiver submission, or list the bucket prefix with `aws s3 ls s3://<waiver-bucket>/<expected-prefix>/` to confirm object presence) or are under a different key than expected.
* **Expired waivers** are not deleted from S3. The 1-year expiration tracked by `waiver_signed_at` only determines whether the kiosk prompts re-signing at the member's next visit — the original signed document remains available in S3 for the full 7-year retention period.
* **`dev` environment waivers** are synthetic test data and must not contain real member information. Do not copy waiver files from `prod` into `dev`.
