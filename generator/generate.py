"""Command-line entry point of the synthetic leasing data generator.

Every table is an independent step: a failure in one table is logged and
reported via the exit code, but does not stop the other tables.

Examples:
    uv run python -m generator.generate --table contracts --date 2026-10-10
    uv run python -m generator.generate --table all --upload --bucket my-bucket
"""

import argparse
import logging
import sys
from collections import Counter
from collections.abc import Callable
from datetime import date
from pathlib import Path

from generator import contracts
from generator.schema import Row, TableSchema
from generator.storage import partition_key, upload_to_s3, write_csv

LOCAL_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_ROWS = 20
DEFAULT_DIRTY_RATE = 0.1
DEFAULT_SEED = 42

Builder = Callable[[date, int, float, int], tuple[list[Row], Counter[str]]]
"""Table builder: (day, n_rows, dirty_rate, seed) -> (raw rows, issue counts)."""

TABLES: dict[str, tuple[TableSchema, Builder]] = {
    "contracts": (contracts.SCHEMA, contracts.build_raw_rows),
}

logger = logging.getLogger("generator")


def run_table(table: str, args: argparse.Namespace) -> Path:
    """Generate one table for one day, write it locally and optionally upload it.

    Args:
        table: Name of the table to generate (a key of ``TABLES``).
        args: Parsed command-line arguments.

    Returns:
        Path of the written local file.
    """
    schema, build = TABLES[table]
    rows, issues = build(args.date, args.rows, args.dirty_rate, args.seed)

    key = partition_key(schema.name, args.date)
    local_path = LOCAL_DATA_DIR / key
    write_csv(rows, schema.columns, local_path)
    logger.info("%s: wrote %d rows -> %s", table, len(rows), local_path)
    logger.info("%s: injected issues: %s", table, dict(sorted(issues.items())) or "none")

    if args.upload:
        upload_to_s3(local_path, args.bucket, key)
        logger.info("%s: uploaded -> s3://%s/%s", table, args.bucket, key)
    return local_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse and validate command-line arguments.

    Args:
        argv: Arguments to parse; defaults to ``sys.argv[1:]``.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Generate synthetic raw leasing data for one day.")
    parser.add_argument("--table", choices=[*TABLES, "all"], default="all",
                        help="table to generate (default: all)")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(),
                        help="business day, YYYY-MM-DD (default: today)")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS,
                        help=f"rows per table per day (default: {DEFAULT_ROWS})")
    parser.add_argument("--dirty-rate", type=float, default=DEFAULT_DIRTY_RATE,
                        help=f"probability 0-1 that a row gets a data issue (default: {DEFAULT_DIRTY_RATE})")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED,
                        help=f"random seed for reproducible output (default: {DEFAULT_SEED})")
    parser.add_argument("--upload", action="store_true", help="upload generated files to S3")
    parser.add_argument("--bucket", help="target S3 bucket (required with --upload)")

    args = parser.parse_args(argv)
    if args.upload and not args.bucket:
        parser.error("--bucket is required with --upload")
    if args.rows < 0:
        parser.error("--rows must be >= 0")
    if not 0 <= args.dirty_rate <= 1:
        parser.error("--dirty-rate must be between 0 and 1")
    return args


def main(argv: list[str] | None = None) -> int:
    """Run the generator for the selected tables.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        Exit code: 0 if every table succeeded, 1 if any table failed.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args(argv)
    tables = list(TABLES) if args.table == "all" else [args.table]

    failed: list[str] = []
    for table in tables:
        try:
            run_table(table, args)
        except Exception:  # noqa: BLE001 – one table must never stop the others
            logger.exception("%s: failed", table)
            failed.append(table)

    if failed:
        logger.error("Failed tables: %s", ", ".join(failed))
        return 1
    logger.info("Done: %s", ", ".join(tables))
    return 0


if __name__ == "__main__":
    sys.exit(main())
