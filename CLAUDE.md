# Project: leasing-analytics-dbt (learning project)

## Goal

Learn dbt (and analytics engineering in general) on a realistic but entirely fictional leasing business. Pipeline: synthetic data generator → S3 (raw layer) → dbt + DuckDB → staging / intermediate / marts models → (optionally) parquet export to S3 and a Power BI view.

This is a learning project, not production. Understanding every step matters more than getting things "done" quickly.

## About me (context for Claude)

- Senior BI Analyst: strong SQL, Power BI, several years of Alteryx (point-and-click ETL workflows).
- I know the leasing process from the business side.
- dbt, Jinja, Git workflow, AWS and DuckDB are new to me or only loosely familiar.
- I learn in short sessions (~45 min in the morning, a longer block on weekends), so work must be split into small, closable steps.

## Working rules

- **Language.** We talk in **Polish** in the Claude Code chat. **Everything that goes into the repo / GitHub is in English**: code, table and column names, comments, docs, README, CLAUDE.md, commit messages, PR descriptions.
- **Explain before doing.** For every new dbt concept (source, ref, materialization, test, macro, snapshot, incremental) briefly explain what it is and why. Where possible compare to Alteryx (e.g. model = container/workflow, `ref()` = connection between tools, test = Test/Filter tool with an alert).
- **Small steps.** One session = one closed step from the milestones below. At the end of a session, propose what's next.
- **Let me write.** For SQL models, first describe what the model should do and let me try; give the full solution when I ask or get stuck. Config, boilerplate and infrastructure scripts can be written right away.
- **Ask before running anything.** Before every terminal command (especially AWS, installs, git) first show what you want to run and why, and wait for my "ok". Without asking you may only read project files and edit files I asked for (using the file edit tools, not the shell). After running, show the output, including errors, and explain it.
- **No secrets in the repo.** No AWS access keys, passwords or tokens in files. AWS access goes through the local AWS CLI config (`~/.aws/`, outside the repo) and DuckDB's `credential_chain`. `profiles.yml` lives outside the repo (`~/.dbt/`) or in the repo without sensitive data.
- **No company data.** All data is generated. The structure may resemble real processes, but no real names, amounts, rules or customers.
- **Ask before costs.** Before proposing anything that may generate AWS costs (new services, large volumes), ask.

## Environment

- **Everything runs locally on Windows 11** (no EC2 – dropped to avoid paying for an always-on server). Claude Code runs locally too.
- **Project folder:** `C:\Users\rkiel\OneDrive\Desktop\leasing-analytics-dbt`. OneDrive is uninstalled – "OneDrive" in the path is just a leftover, nothing syncs. The venv (`.venv/`) and the `.duckdb` file live in the project folder (both git-ignored).
- **AWS:** S3 only, region `us-east-1`. Bucket: `leasing-dbt-radeq-2026` (Block all public access: ON, no versioning, SSE-S3). Laptop access via IAM user `leasing-dbt-local` with an inline policy scoped to that one bucket; keys only in `C:\Users\rkiel\.aws\credentials` (outside the repo), dbt reads them via `credential_chain`. Guide: [docs/01-aws-s3-setup.md](docs/01-aws-s3-setup.md).
- **GitHub:** https://github.com/Radeq2137/leasing-analytics-dbt (public, portfolio).
- **Editor:** VS Code, locally.
- **Stack:**
  - Python 3.11+ in a virtual environment (uv)
  - dbt-core + dbt-duckdb
  - DuckDB with httpfs and parquet extensions (reading from S3)
  - AWS CLI v2
  - Git + GitHub
  - optionally the "dbt Power User" VS Code extension

## Architecture

```
generator (local, catch-up mode: fills in missing days from the last dt in S3 up to today)
  → s3://<bucket>/raw/<table>/dt=YYYY-MM-DD/<table>.csv
  → dbt-duckdb locally (sources with external_location = read_csv('s3://...', hive_partitioning=true))
  → staging      (1 model per source: types, names, cleaning)
  → intermediate (joins, business logic)
  → marts        (facts and dimensions for BI)
  → local .duckdb file + optionally parquet to s3://<bucket>/marts/
```

Running the generator: manually for now (at the start of a session) or via Windows Task Scheduler; later (Stage 5) GitHub Actions on a schedule + OIDC to AWS (no stored keys).

Config sketch (to verify against the current dbt-duckdb README):

```yaml
# ~/.dbt/profiles.yml
leasing:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: C:/Users/rkiel/OneDrive/Desktop/leasing-analytics-dbt/leasing.duckdb
      extensions: [httpfs, parquet]
      secrets:
        - type: s3
          provider: credential_chain
          region: us-east-1
```

```yaml
# models/staging/sources.yml
version: 2
sources:
  - name: raw
    meta:
      external_location: "read_csv('s3://<bucket>/raw/{name}/*/*.csv', header=true, hive_partitioning=true)"
    tables:
      - name: customers
      - name: contracts
      - name: installment_schedule
      - name: payments
```

## Data domain (fictional leasing)

Source tables, generated daily (incrementally). Names in English, snake_case:

| table | description | key fields |
|---|---|---|
| customers | companies and individuals leasing assets | customer_id, customer_type (company/individual), industry, region, registration_date |
| contracts | lease contracts | contract_id, customer_id, signed_date, asset_type (car/machinery/IT/...), net_value, term_months, down_payment_pct, status |
| installment_schedule | repayment plan per contract | contract_id, installment_no, due_date, installment_amount |
| payments | actual payments received | payment_id, contract_id, payment_date, amount |

Contract statuses: `active`, `closed`, `collections`, `terminated`.

**Intentionally dirty data** (the generator injects it with a small probability so tests have something to catch):

- duplicate contract_id,
- empty or negative amounts,
- payments to non-existent contracts,
- dates in the future,
- inconsistent casing in statuses / industries.

**Target marts (examples):**

- `dim_customer`, `dim_date`, `fct_contracts`, `fct_payments`
- `mart_portfolio_monthly` – portfolio value, number of active contracts per month
- `mart_delinquency` – DPD (days past due), buckets 0 / 1-30 / 31-60 / 61-90 / 90+

## Data generator

- Python + Faker (easier to keep consistent relations customer → contract → schedule → payments).
- Incremental in **catch-up** mode: checks the last `dt=` partition in S3 and generates every missing day up to today (each day separately, keeping state – the list of existing customers/contracts in a small state file or read from S3). Each day: new customers and contracts, payments (some late), contract status changes, some dirty records.
- Parameters: new customers/contracts per day, dirty-record rate, random seed (`--seed`) for reproducibility.
- `--backfill N` mode – on the first run generate history for the last N days (e.g. 90).
- Run locally (manually / Windows Task Scheduler), later GitHub Actions.

## Repo structure (target)

```
leasing-analytics-dbt/
├── CLAUDE.md
├── README.md
├── docs/
├── generator/
│   ├── generate.py
│   └── requirements.txt
├── dbt/
│   ├── dbt_project.yml
│   ├── models/
│   │   ├── staging/
│   │   ├── intermediate/
│   │   └── marts/
│   ├── tests/
│   ├── macros/
│   ├── snapshots/
│   └── seeds/             (e.g. lookups: asset types, regions)
└── .gitignore             (venv, *.duckdb, target/, logs/, .env)
```

## Milestones

Tick as you go (`[x]`).

**Stage 0 – environment**
- [x] Decisions: no EC2, everything local, catch-up generator
- [x] AWS: root MFA, budget alert, S3 bucket (us-east-1)
- [x] AWS: IAM user with a single-bucket policy, access key, AWS CLI v2, tests pass
- [x] GitHub repo, .gitignore, first commit
- [ ] Python via uv, venv in the project (`.venv/`), install dbt-core + dbt-duckdb

**Stage 1 – data in S3**
- [ ] Minimal generator (contracts only) → S3 with `dt=` partitions
- [ ] Extend to customers, installment_schedule, payments with consistent relations
- [ ] Dirty data + `--backfill` + catch-up mode (+ optionally Windows Task Scheduler)

**Stage 2 – dbt basics**
- [ ] `dbt init`, `dbt debug` passes, DuckDB reads from S3
- [ ] Sources + staging models for all tables
- [ ] Generic tests: unique, not_null, relationships, accepted_values
- [ ] `dbt docs generate` + review the lineage graph

**Stage 3 – business logic**
- [ ] Intermediate models (e.g. contract + schedule + payments)
- [ ] Marts: dimensions, facts, monthly portfolio, DPD delinquency
- [ ] Custom (singular) tests for business rules, e.g. sum of installments = financed amount

**Stage 4 – advanced dbt**
- [ ] Jinja and macros (e.g. a DPD bucket macro)
- [ ] Incremental model for payments
- [ ] Snapshot (SCD2) on contract statuses
- [ ] Packages (dbt_utils, possibly dbt_expectations)

**Stage 5 – final / optional**
- [ ] Export marts to parquet in S3
- [ ] Power BI view (via parquet / ODBC to DuckDB)
- [ ] GitHub Actions: scheduled daily generator run + OIDC to AWS, no keys in the repo
- [ ] README as a portfolio project description
- [ ] (optional) Switch to a Snowflake trial with an external stage on the same bucket and dbt-snowflake

## Decisions

- **2026-10-09:** Claude Code and everything else runs locally, no EC2.
- **2026-10-09:** Generator in Python + Faker.
- **2026-10-10:** Everything in the repo is in English, including table and column names (good for an international portfolio). Chat stays in Polish.

## Status

Update at the end of every session: what was done, what is in progress, next step.

- **2026-10-09:** Wrote CLAUDE.md. Decisions: no EC2, everything local, catch-up generator, GitHub Actions later. Done: EC2 removed, root MFA, USD 0.01 budget with alerts, bucket in us-east-1.
- **2026-10-10:** IAM user `leasing-dbt-local` + single-bucket policy, AWS CLI v2 configured (`aws configure`, default profile). Tests: get-caller-identity OK, ls/cp/rm on the bucket OK, `aws s3 ls` → AccessDenied (as intended). Repo connected to GitHub; README, .gitignore, CLAUDE.md, docs/ committed in English. **Next step:** Python via `uv`, venv in the project (`.venv/`), install dbt-core + dbt-duckdb.
