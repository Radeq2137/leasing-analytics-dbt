# leasing-analytics-dbt

A learning project: an end-to-end **analytics engineering** pipeline built with **dbt** on a fully **fictional** leasing business.
All data is synthetic – no company data and no real customers.

## Architecture

```
generator (Python + Faker, catch-up mode: fills in missing days)
   │
   ▼
S3  s3://<bucket>/raw/<table>/dt=YYYY-MM-DD/<table>.csv
   │
   ▼
dbt + DuckDB (local, reading directly from S3)
   ├── staging       – types, naming, cleaning (1 model per source)
   ├── intermediate  – joins, business logic
   └── marts         – facts and dimensions for BI
   │
   ▼
Power BI (parquet / DuckDB)
```

## Data domain

| table | description |
|---|---|
| `customers` | companies and individuals leasing assets |
| `contracts` | lease contracts (asset type, value, term, status) |
| `installment_schedule` | repayment plan per contract |
| `payments` | actual payments received |

The generator intentionally injects **dirty data** (duplicates, negative amounts, payments to non-existent contracts, future dates, inconsistent casing) so the dbt tests have something to catch.

Target marts: `dim_customer`, `dim_date`, `fct_contracts`, `fct_payments`, `mart_portfolio_monthly`, `mart_delinquency` (DPD buckets 0 / 1–30 / 31–60 / 61–90 / 90+).

## Stack

Python · Faker · AWS S3 · AWS CLI · dbt-core · dbt-duckdb · DuckDB · Git / GitHub · Power BI

## Security

- No secrets in the repo – S3 access through an IAM user with a least-privilege policy scoped to a single bucket; keys stored only locally in `~/.aws/`.
- Private bucket (Block Public Access) and a budget alert on the AWS account.

## Progress

- [x] **Stage 0** – AWS: S3 bucket, IAM user (least privilege), AWS CLI, GitHub repo
- [x] **Stage 0** – Python 3.12 (uv), dbt-core + dbt-duckdb
- [ ] **Stage 1** – data generator → S3
- [ ] **Stage 2** – dbt basics: sources, staging, generic tests, docs
- [ ] **Stage 3** – business logic: intermediate, marts, singular tests
- [ ] **Stage 4** – macros, incremental models, snapshots (SCD2), packages
- [ ] **Stage 5** – parquet export, Power BI, GitHub Actions

## Documentation

- [docs/01-aws-s3-setup.md](docs/01-aws-s3-setup.md) – step-by-step S3 setup and laptop access
