#!/usr/bin/env python3
"""Run Aurora migrations via the RDS Data API.

Each migration file in db/migrations/ is idempotent (uses IF NOT EXISTS /
DROP IF EXISTS patterns), so all files are applied on every run. This means
the script is safe to re-run after partial failures.

Required environment variables:
    CLUSTER_ARN   Aurora cluster ARN
    SECRET_ARN    Secrets Manager ARN for the Aurora master credentials

Optional environment variables:
    DATABASE      Database name (default: osc)
    AWS_PROFILE   AWS CLI profile (default: outdoorsportsclub)
    AWS_REGION    AWS region (default: us-east-1)

Usage:
    python3 scripts/migrate.py
    python3 scripts/migrate.py --dry-run   # parse only, no AWS calls
"""
import argparse
import logging
import os
import re
import sys
from pathlib import Path

import boto3
import botocore.exceptions

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent.parent / "db" / "migrations"


def split_statements(sql: str) -> list[str]:
    """Split a SQL file into individual statements.

    Strips line comments and splits on semicolons. Intentionally simple:
    all migrations in this project use only DDL and DML with no dollar-quoted
    function bodies, so splitting on ';' is safe.
    """
    sql = re.sub(r"--[^\n]*", "", sql)
    return [s.strip() for s in sql.split(";") if s.strip()]


def run_migrations(dry_run: bool = False) -> None:
    cluster_arn = os.environ.get("CLUSTER_ARN")
    secret_arn = os.environ.get("SECRET_ARN")

    if not cluster_arn:
        log.error("CLUSTER_ARN environment variable is required")
        sys.exit(1)
    if not secret_arn:
        log.error("SECRET_ARN environment variable is required")
        sys.exit(1)

    database = os.environ.get("DATABASE", "osc")
    profile = os.environ.get("AWS_PROFILE", "outdoorsportsclub")
    region = os.environ.get("AWS_REGION", "us-east-1")

    if dry_run:
        log.info("DRY RUN — SQL will be parsed but not executed")

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        log.error("No migration files found in %s", MIGRATIONS_DIR)
        sys.exit(1)

    log.info(
        "Applying %d migration file(s) to %s / %s",
        len(migration_files),
        cluster_arn,
        database,
    )

    # Defer boto3 session creation so --dry-run works without AWS credentials.
    rds = None
    if not dry_run:
        session = boto3.session.Session(profile_name=profile, region_name=region)
        rds = session.client("rds-data")

    total_statements = 0

    for path in migration_files:
        sql = path.read_text(encoding="utf-8")
        statements = split_statements(sql)

        if not statements:
            log.warning("  %s — no statements found, skipping", path.name)
            continue

        log.info("  %s (%d statement(s))", path.name, len(statements))

        for i, stmt in enumerate(statements, start=1):
            log.debug("    [%d] %.120s", i, stmt)

            if dry_run:
                continue

            try:
                rds.execute_statement(
                    resourceArn=cluster_arn,
                    secretArn=secret_arn,
                    database=database,
                    sql=stmt,
                    continueAfterTimeout=True,
                )
            except botocore.exceptions.ClientError as exc:
                log.error(
                    "Statement %d in %s failed: %s",
                    i,
                    path.name,
                    exc.response["Error"]["Message"],
                )
                log.error("Failed statement:\n%s", stmt)
                sys.exit(1)

        total_statements += len(statements)

    if dry_run:
        log.info(
            "Dry run complete — %d statement(s) parsed across %d file(s)",
            total_statements,
            len(migration_files),
        )
    else:
        log.info(
            "All %d migration(s) applied successfully (%d statement(s) total)",
            len(migration_files),
            total_statements,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Aurora migrations via the RDS Data API")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse migration files and print statements without executing them",
    )
    args = parser.parse_args()
    run_migrations(dry_run=args.dry_run)
