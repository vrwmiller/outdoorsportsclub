# Database Backup and Point-in-Time Restore

**Audience:** Webmaster (Level 6).

This runbook covers how to restore the Aurora Serverless v2 database from backup. There are two restore paths — always attempt PITR first. The AWS Backup daily snapshot is a last resort.

See `docs/design.md` Section 8 for the full DR architecture, RPO/RTO targets, and the "Red Button" procedure.

---

## RPO and RTO targets

| Target | Value |
| :--- | :--- |
| RPO (acceptable data loss) | ~5 minutes — Aurora PITR is the primary path |
| RTO (time to restore) | Under 60 minutes from a cold start |

---

## Part A — Point-in-time restore (preferred)

Aurora PITR restores to within approximately 5 minutes of a failure. Use this path whenever the Aurora cluster's storage is accessible.

### 1. Identify the restore point

Determine the timestamp to restore to — typically just before the failure event or data corruption was detected. Timestamps are in UTC.

### 2. Initiate the restore

```bash
aws rds restore-db-cluster-to-point-in-time \
  --db-cluster-identifier <restored-cluster-id> \
  --source-db-cluster-identifier <original-cluster-id> \
  --restore-to-time "2026-03-16T04:00:00Z" \
  --profile outdoorsportsclub
```

Replace:

* `<restored-cluster-id>` — a new identifier for the restored cluster (e.g., `odsc-prod-restored-20260316`)
* `<original-cluster-id>` — the identifier of the failed cluster
* `--restore-to-time` — the UTC timestamp of the restore point

PITR creates a new Aurora cluster; it does **not** modify the original.

### 3. Wait for the cluster to become available

Monitor the restore status:

```bash
aws rds describe-db-clusters \
  --db-cluster-identifier <restored-cluster-id> \
  --query 'DBClusters[0].Status' \
  --profile outdoorsportsclub
```

Wait until `Status` returns `available`. This typically takes 5–20 minutes.

### 4. Add a DB instance to the restored cluster

A PITR-restored cluster has no DB instances. Add one:

```bash
aws rds create-db-instance \
  --db-instance-identifier <restored-cluster-id>-instance-1 \
  --db-cluster-identifier <restored-cluster-id> \
  --db-instance-class db.serverless \
  --engine aurora-postgresql \
  --profile outdoorsportsclub
```

Wait for `Status = available` on the new instance:

```bash
aws rds describe-db-instances \
  --db-instance-identifier <restored-cluster-id>-instance-1 \
  --query 'DBInstances[0].DBInstanceStatus' \
  --profile outdoorsportsclub
```

### 5. Update the Lambda connection endpoint

The restored cluster has a new endpoint. Update the **AWS Secrets Manager** `db-credentials` secret to point Lambda functions at the restored cluster (see the [secrets rotation runbook](secrets-rotation.md) Part B, Steps 3–4). Update the `host` field to the new cluster's writer endpoint.

### 6. Verify

Run a read query against the restored cluster via the AWS console **Query Editor** or RDS Data API to confirm data integrity. Spot-check a few `activity_logs` rows near the restore timestamp to confirm expected records are present.

### 7. Decommission the failed cluster

After confirming the restored cluster is healthy and all Lambda functions are pointed at it, delete the original failed cluster:

```bash
aws rds delete-db-cluster \
  --db-cluster-identifier <original-cluster-id> \
  --skip-final-snapshot \
  --profile outdoorsportsclub
```

> Only skip the final snapshot if the original cluster's storage is corrupt or inaccessible. If the original cluster is healthy (e.g., data corruption at the application level), take a final snapshot first by omitting `--skip-final-snapshot`.

---

## Part B — AWS Backup snapshot restore (last resort)

Use this path **only if Aurora PITR is unavailable** — for example, if the source cluster's storage has been destroyed and transaction logs are not accessible. Maximum data loss: up to approximately 24 hours (snapshots run daily at 02:00 UTC).

### 1. Find the most recent snapshot

```bash
aws backup list-recovery-points-by-backup-vault \
  --backup-vault-name <vault-name> \
  --by-resource-type Aurora \
  --profile outdoorsportsclub
```

Note the `RecoveryPointArn` of the most recent recovery point before the failure.

### 2. Restore from the recovery point

```bash
aws backup start-restore-job \
  --recovery-point-arn <recovery-point-arn> \
  --metadata '{"DBClusterIdentifier":"<restored-cluster-id>","Engine":"aurora-postgresql"}' \
  --iam-role-arn <backup-role-arn> \
  --profile outdoorsportsclub
```

Monitor the restore job:

```bash
aws backup describe-restore-job \
  --restore-job-id <job-id> \
  --profile outdoorsportsclub
```

### 3. Follow Steps 3–7 from Part A

Once the cluster is `available`, add a DB instance, update the secrets endpoint, verify, and decommission the original cluster as described in Part A.

---

## Post-restore checklist

* [ ] Lambda functions are writing to the restored cluster (check **Amazon CloudWatch Logs** for DB errors)
* [ ] **Amazon CloudWatch Alarm** for Aurora ACU is not firing unexpectedly
* [ ] A spot-check of `activity_logs` confirms the expected data boundary (records up to the restore point are present)
* [ ] The **AWS Secrets Manager** `db-credentials` secret `host` field points to the new cluster endpoint
* [ ] The old cluster has been decommissioned or snapshotted and deleted
* [ ] If restored to `dev`: confirm no real member data was imported — `dev` must contain only synthetic data (required by GDPR/CCPA compliance; see `docs/design.md` Section 8, "Non-production environment")

---

## Notes

* **Aurora PITR is continuous** — no manual snapshot is required to enable it. The 35-day window is always available as long as the cluster's storage remains accessible.
* **AWS Backup vault lock (prod only):** The prod backup vault has Compliance Mode vault lock enabled — snapshots cannot be deleted before retention expires, even by an Administrator. This is intentional and provides an independent safety net against accidental deletion.
* **Cross-region copy:** AWS Backup copies daily snapshots to every region in `RegionList`. If the primary region is completely inaccessible, the cross-region snapshot in `us-east-2` (if multi-region is enabled) can be used as the source for Part B.
* **Active-active failover (if multi-region is enabled):** Aurora Global Database promotes the secondary region automatically — this runbook does not apply in that path. This runbook covers single-region restore scenarios only.
