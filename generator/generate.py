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

from generator import contracts, customers
from generator.days import missing_days
from generator.schema import Row, TableSchema
from generator.storage import list_existing_days, partition_key, upload_to_s3, write_csv

LOCAL_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_ROWS = 20
DEFAULT_DIRTY_RATE = 0.1
DEFAULT_SEED = 42

Builder = Callable[[date, int, float, int], tuple[list[Row], Counter[str]]]
"""Table builder: (day, n_rows, dirty_rate, seed) -> (raw rows, issue counts)."""

TABLES: dict[str, tuple[TableSchema, Builder]] = {
    "customers": (customers.SCHEMA, customers.build_raw_rows),
    "contracts": (contracts.SCHEMA, contracts.build_raw_rows),
}

logger = logging.getLogger("generator")


def days_to_generate(table: str, args: argparse.Namespace) -> list[date]:
    """Decide which business days to generate for one table.

    Args:
        table: Table name (a key of ``TABLES``).
        args: Parsed command-line arguments.

    Returns:
        With ``--catch-up``: the days missing in S3 (see ``missing_days``). On an empty table,
        ``--backfill N`` gives the last N days and ``--backfill-from DATE`` every day from DATE
        up to today. Without ``--catch-up``: just ``--date``.
    """
    if not args.catch_up:
        return [args.date]
    today = date.today()
    backfill_days = args.backfill
    if args.backfill_from is not None:
        backfill_days = (today - args.backfill_from).days + 1  # DATE itself is the first day
    existing = list_existing_days(args.bucket, table)
    return missing_days(existing, today=today, backfill_days=backfill_days)


def run_table_day(table: str, day: date, args: argparse.Namespace) -> Path:
    """Generate one table for one day, write it locally and optionally upload it.

    Args:
        table: Name of the table to generate (a key of ``TABLES``).
        day: Business day to generate.
        args: Parsed command-line arguments.

    Returns:
        Path of the written local file.
    """
    schema, build = TABLES[table]
    seed = args.seed + day.toordinal()  # different per day, still reproducible
    rows, issues = build(day, args.rows, args.dirty_rate, seed)

    key = partition_key(schema.name, day)
    local_path = LOCAL_DATA_DIR / key
    write_csv(rows, schema.columns, local_path)
    logger.info("%s %s: wrote %d rows -> %s", table, day, len(rows), local_path)
    logger.info("%s %s: injected issues: %s", table, day, dict(sorted(issues.items())) or "none")

    if args.upload:
        upload_to_s3(local_path, args.bucket, key)
        logger.info("%s %s: uploaded -> s3://%s/%s", table, day, args.bucket, key)
    return local_path


def run_table(table: str, args: argparse.Namespace) -> None:
    """Generate every planned day of one table, oldest first.

    A failing day stops this table (the error goes up to ``main``):
    ``missing_days()`` continues after the latest day in S3, so a skipped
    day would never be filled in later.

    Args:
        table: Name of the table to generate (a key of ``TABLES``).
        args: Parsed command-line arguments.
    """
    days = days_to_generate(table, args)
    if not days:
        logger.info("%s: up to date, nothing to do", table)
        return

    logger.info("%s: %d day(s) to generate: %s .. %s", table, len(days), days[0], days[-1])
    if args.dry_run:
        return

    for day in days:
        run_table_day(table, day, args)

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
    
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--date", type=date.fromisoformat, default=date.today(),
                      help="business day, YYYY-MM-DD (default: today)")
    mode.add_argument("--catch-up", action="store_true",
                      help="generate every day missing in S3, up to today (needs --upload)")
    history = parser.add_mutually_exclusive_group()
    history.add_argument("--backfill", type=int, metavar="N",
                         help="with --catch-up and no data yet: generate the last N days")
    history.add_argument("--backfill-from", type=date.fromisoformat, metavar="DATE",
                         help="with --catch-up and no data yet: generate every day from DATE up to today "
                              "(use the go-live date for tables that depend on the customer timeline)")
    parser.add_argument("--dry-run", action="store_true",
                        help="only print which days would be generated")
    
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS,
                        help=f"contracts per day (default: {DEFAULT_ROWS}); ignored by customers, whose "
                             "number per day follows the registration timeline")
    parser.add_argument("--dirty-rate", type=float, default=DEFAULT_DIRTY_RATE,
                        help=f"probability 0-1 that a row gets a data issue (default: {DEFAULT_DIRTY_RATE})")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED,
                        help=f"random seed for reproducible output (default: {DEFAULT_SEED})")
    parser.add_argument("--upload", action="store_true", help="upload generated files to S3")
    parser.add_argument("--bucket", help="target S3 bucket (required with --upload)")

    args = parser.parse_args(argv)
    if args.catch_up and not args.upload:
        parser.error("--catch-up needs --upload (existing days are read from S3)")
    if (args.backfill is not None or args.backfill_from is not None) and not args.catch_up:
        parser.error("--backfill and --backfill-from only work together with --catch-up")
    if args.backfill is not None and args.backfill < 1:
        parser.error("--backfill must be >= 1")
    if args.backfill_from is not None and args.backfill_from > date.today():
        parser.error("--backfill-from must not be in the future")
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
