"""Synthetic leasing data generator – minimal version (contracts only).

Generates lease contracts signed on a single day, writes them to a local CSV
in a Hive-style partition (dt=YYYY-MM-DD) and optionally uploads it to S3.

Examples:
    uv run python generator/generate.py --date 2026-10-10 --n-contracts 20 --seed 42
    uv run python generator/generate.py --date 2026-10-10 --upload --bucket my-bucket
"""

import argparse
import csv
import random
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCAL_DATA_DIR = PROJECT_ROOT / "data"

# asset_type -> (weight, min net value, max net value) in PLN
ASSET_TYPES = {
    "car": (50, 60_000, 250_000),
    "truck": (10, 200_000, 600_000),
    "machinery": (20, 100_000, 1_500_000),
    "it_equipment": (15, 10_000, 150_000),
    "medical_equipment": (5, 50_000, 800_000),
}
TERM_MONTHS = [24, 36, 48, 60]
DOWN_PAYMENT_PCT = [0, 10, 20, 30]

CONTRACT_COLUMNS = [
    "contract_id",
    "customer_id",
    "signed_date",
    "asset_type",
    "net_value",
    "term_months",
    "down_payment_pct",
    "status",
]


def generate_contracts(day: date, n_contracts: int, rng: random.Random) -> list[dict]:
    asset_names = list(ASSET_TYPES)
    weights = [ASSET_TYPES[a][0] for a in asset_names]

    contracts = []
    for i in range(1, n_contracts + 1):
        asset_type = rng.choices(asset_names, weights=weights)[0]
        _, min_value, max_value = ASSET_TYPES[asset_type]
        contracts.append(
            {
                # Unique without any state: date + sequence number within the day.
                "contract_id": f"CT-{day:%Y%m%d}-{i:04d}",
                # Placeholder until the customers table exists.
                "customer_id": f"CU-{rng.randint(1, 500):05d}",
                "signed_date": day.isoformat(),
                "asset_type": asset_type,
                "net_value": round(rng.uniform(min_value, max_value), 2),
                "term_months": rng.choice(TERM_MONTHS),
                "down_payment_pct": rng.choice(DOWN_PAYMENT_PCT),
                "status": "active",
            }
        )
    return contracts


def partition_key(table: str, day: date) -> str:
    return f"raw/{table}/dt={day.isoformat()}/{table}.csv"


def write_csv(rows: list[dict], columns: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def upload_to_s3(path: Path, bucket: str, key: str) -> None:
    import boto3  # imported here so local-only runs don't need AWS at all

    # Credentials come from the default chain (~/.aws/credentials locally,
    # OIDC role in GitHub Actions) – never from this code.
    boto3.client("s3").upload_file(str(path), bucket, key)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(),
                        help="business date to generate (YYYY-MM-DD), default: today")
    parser.add_argument("--n-contracts", type=int, default=20,
                        help="number of contracts signed that day (default: 20)")
    parser.add_argument("--seed", type=int, default=42,
                        help="random seed for reproducible output (default: 42)")
    parser.add_argument("--upload", action="store_true",
                        help="upload the generated file to S3")
    parser.add_argument("--bucket", help="target S3 bucket (required with --upload)")
    args = parser.parse_args()
    if args.upload and not args.bucket:
        parser.error("--bucket is required with --upload")
    return args


def main() -> None:
    args = parse_args()
    # Seed per day, so each day is reproducible on its own.
    rng = random.Random(args.seed * 100_000 + args.date.toordinal())

    contracts = generate_contracts(args.date, args.n_contracts, rng)
    key = partition_key("contracts", args.date)
    local_path = LOCAL_DATA_DIR / key
    write_csv(contracts, CONTRACT_COLUMNS, local_path)
    print(f"Wrote {len(contracts)} contracts -> {local_path}")

    if args.upload:
        upload_to_s3(local_path, args.bucket, key)
        print(f"Uploaded -> s3://{args.bucket}/{key}")


if __name__ == "__main__":
    main()
