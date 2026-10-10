"""Writing raw files locally and uploading them to S3."""

import csv
from datetime import date
from pathlib import Path

from generator.schema import Row


def partition_key(table: str, day: date) -> str:
    """Build the Hive-style key of a table's file for one day.

    Args:
        table: Table name.
        day: Business day.

    Returns:
        Key like ``raw/contracts/dt=2026-10-10/contracts.csv``, used both as
        the local path (under the data directory) and as the S3 key.
    """
    return f"raw/{table}/dt={day.isoformat()}/{table}.csv"


def write_csv(rows: list[Row], columns: tuple[str, ...], path: Path) -> None:
    """Write rows to a UTF-8 CSV file with a header, creating folders as needed.

    Args:
        rows: Rows to write; every row must have exactly ``columns`` as keys.
        columns: Column names, in file order.
        path: Target file; overwritten if it exists.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def upload_to_s3(path: Path, bucket: str, key: str) -> None:
    """Upload a local file to S3.

    Credentials come from the default AWS chain (``~/.aws/credentials``
    locally, an OIDC role in GitHub Actions) and never from this code.

    Args:
        path: Local file to upload.
        bucket: Target bucket name.
        key: Target object key.

    Raises:
        botocore.exceptions.BotoCoreError: On missing credentials or network errors.
        botocore.exceptions.ClientError: On AWS-side errors, e.g. access denied.
    """
    import boto3  # Imported lazily so local-only runs don't need AWS at all.

    boto3.client("s3").upload_file(str(path), bucket, key)
