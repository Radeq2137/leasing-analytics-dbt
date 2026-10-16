# Project: leasing-analytics-dbt (learning project)

## Goal

Learn dbt (and analytics engineering in general) on a realistic but entirely fictional leasing business. Pipeline: synthetic data generator → S3 (raw layer) → dbt + DuckDB → staging / intermediate / marts models → (optionally) parquet export to S3 and a Power BI view.

This is a learning project, not production. Understanding every step matters more than getting things "done" quickly.

## About me (context for Claude)

- Senior BI Analyst: strong SQL, Power BI, several years of Alteryx (point-and-click ETL workflows).
- I know the leasing process from the business side.
- dbt, Jinja, Git workflow, AWS and DuckDB are new to me or only loosely familiar.
- Career goal: move towards **data engineering**. Prefer solutions and explanations that build DE skills (Python, pandas/DuckDB/polars, S3, testing, CI, orchestration), not only analytics.
- I learn in short sessions (~45 min in the morning, a longer block on weekends), so work must be split into small, closable steps.

## Working rules

- **Language.** We talk in **Polish** in the Claude Code chat. **Everything that goes into the repo / GitHub is in English**: code, table and column names, comments, docs, README, CLAUDE.md, commit messages, PR descriptions.
- **Welcome-back summary.** When I return after a break ("hej, wróciłem, co ostatnio zrobiliśmy i co dalej?"), first read the Status and Milestones sections and summarize in Polish: what was done last time, where we are in the milestones, what the next step is (and roughly how long it takes). Don't run anything before I confirm.
- **Python learning track.** Alongside the project I learn Python from scratch in `learning/python/` (git-ignored, local only; modules 1–11, see its README): cheat sheet with SQL/Alteryx analogies + exercise file with stubs + pytest tests, 10–15 min each, leasing-themed. Help order: I try first → hint → solution only when I ask. **Cumulative modules:** every module = new topic + review exercises mixing earlier modules + one refactor of an earlier solution with the new tool; a checkpoint task after every 3 modules (see `learning/python/README.md`). Nothing is learned in isolation. **Adaptive drills:** when I paste my code + pytest output, log the mistakes in `learning/python/weak_spots.md` and generate targeted, gradually harder `drill_NN_<topic>.py` exercises (cumulative by default, isolated on one topic if I ask). Update the module status table in `learning/python/README.md` as I finish modules.
- **Explain before doing.** For every new dbt concept (source, ref, materialization, test, macro, snapshot, incremental) briefly explain what it is and why. Where possible compare to Alteryx (e.g. model = container/workflow, `ref()` = connection between tools, test = Test/Filter tool with an alert).
- **Small steps.** One session = one closed step from the milestones below. At the end of a session, propose what's next.
- **Let me write.** For SQL models, first describe what the model should do and let me try; give the full solution when I ask or get stuck. Config, boilerplate and infrastructure scripts can be written right away.
- **Python: guided, not from scratch.** I understand the logic well, but I get lost in Python syntax. For Python exercises: I state the logic in plain words, you translate it side by side ("logic → Python", line by line, with a short explanation of each construct and SQL/Alteryx analogies); I type it in, run it in the REPL / pytest and review it. Blanks (`___`) only for small, clearly isolated pieces.
- **Ask before running anything.** Before every terminal command (especially AWS, installs, git) first show what you want to run and why, and wait for my "ok". Without asking you may only read project files and edit files I asked for (using the file edit tools, not the shell). After running, show the output, including errors, and explain it.
- **Pythonic code, written for a reviewer.** I review the code, so: PEP 8, type hints on every function, a docstring on every module/function/class (Google style: summary, `Args:`, `Returns:`, `Raises:`), small single-purpose functions, `logging` instead of `print`, no magic numbers (named constants). Explain non-obvious decisions in comments.
- **Best practices first.** Follow [docs/03-engineering-guidelines.md](docs/03-engineering-guidelines.md) in this priority: Python best practices → pandas best practices (pandas 3.x: Copy-on-Write, `.loc`, `str` dtype, vectorize, method chaining) → data engineering best practices (idempotency, partitions, contracts, quarantine, observability). When teaching, name the practice and why it exists.
- **Independent workflows.** Every step (each table in the generator, each dbt model branch, each CI job) must be able to run and fail on its own: one failure must not stop unrelated steps. Steps exchange data through S3 / files, not in-memory state; failures are logged and reported via exit code, and downstream steps work on the last good data.
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
  - Python 3.12 in a project virtual environment managed by uv (`pyproject.toml` + `uv.lock`; run tools with `uv run ...`, e.g. `uv run dbt --version`). uv was installed with winget; its folder is on the user PATH, so a fresh shell finds `uv` (an older shell may need the full path under `%LOCALAPPDATA%\Microsoft\WinGet\Packages\astral-sh.uv_*`).
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

**The detailed, binding schema and data-quality rules live in [docs/02-data-contract.md](docs/02-data-contract.md)** (mandatory columns, `<unknown>` sentinel, `INCLUDE_IN_STATS` Y/N flag, rejected-rows quarantine, read raw as all-varchar). The table below is just an overview.

Source tables, generated daily (incrementally). Names in English, snake_case:

| table | description | key fields |
|---|---|---|
| customers | companies and individuals leasing assets | customer_id, customer_type (company/individual), industry, region, registration_date |
| contracts | lease contracts (flat extract, includes customer & vendor attributes) | transaction_id, contract_id, customer_id, customer_type, customer_email, vendor_id, vendor_type, asset_type, asset_price, net_value, down_payment_pct, term_months, signed_date, delivery_* address, status, INCLUDE_IN_STATS (Y/N) |
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
- [x] Python via uv, venv in the project (`.venv/`), install dbt-core + dbt-duckdb

**Stage 1 – data in S3**
- [x] Minimal generator (contracts only) → S3 with `dt=` partitions (PR #3)
- [x] Dirty data (catalog per data contract)
- [x] `missing_days()` – pure function choosing which days to generate (PR #4)
- [x] `--backfill N` + `--catch-up` + `--dry-run` wired into the generator (S3 partition listing); 90 days of `contracts` in S3 (2026-07-19 .. 2026-10-16) (optionally: Windows Task Scheduler)
- [ ] Extend to customers, installment_schedule, payments with consistent relations – **after the first dbt pass on `contracts`** (see Decisions, 2026-10-16)

**Stage 2 – dbt basics**
- [ ] `dbt init`, `dbt debug` passes, DuckDB reads from S3
- [ ] Source + staging model for `contracts` first; then one staging model for each new table as it is added
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
- **2026-10-10:** Git workflow: one feature branch per session (`feature/<topic>`), pushed to GitHub and merged into `main` via a Pull Request. Commits keep the `Co-Authored-By: Claude` trailer.
- **2026-10-16:** Order of work: dbt starts early. After `--backfill` / catch-up for `contracts`, do Stage 2 on `contracts` alone, then add the other tables one by one (generator table + its staging model + tests together). Reason: the "source → model → test" loop is the core data-engineering skill and should be practised early, not after weeks of generator work.

## Status

Update at the end of every session: what was done, what is in progress, next step.

- **2026-10-09:** Wrote CLAUDE.md. Decisions: no EC2, everything local, catch-up generator, GitHub Actions later. Done: EC2 removed, root MFA, USD 0.01 budget with alerts, bucket in us-east-1.
- **2026-10-10:** IAM user `leasing-dbt-local` + single-bucket policy, AWS CLI v2 configured (`aws configure`, default profile). Tests: get-caller-identity OK, ls/cp/rm on the bucket OK, `aws s3 ls` → AccessDenied (as intended). Repo connected to GitHub; README, .gitignore, CLAUDE.md, docs/ committed in English. 
- **Session 3:** Branch `feature/python-dbt-setup`. Installed uv 0.13.0 (winget), Python 3.12.12, project `pyproject.toml` + `uv.lock`, `.venv/` with dbt-core 1.12.5 + dbt-duckdb 1.11.0 (duckdb 1.5.6). `uv run dbt --version` OK. **Stage 0 complete.** PR #1 (`feature/python-dbt-setup`) opened. **Next step:** Stage 1 – minimal generator (contracts only) → S3 with `dt=` partitions (adds Faker + boto3 via `uv add`).
- **GitHub Actions – on hold:** a CI workflow (`.github/workflows/ci.yml`: `uv sync --locked` + `uv run dbt --version`, on pull_request + workflow_dispatch) is merged to `main` (PR #2). Jobs don't start: the GitHub account is billing-locked by an old declined USD 10 payment (2024-02-19). A GitHub Support ticket was sent. Red/failed CI checks are expected until Support replies; then re-run. Still to do afterwards: OIDC provider + IAM role `github-actions-leasing-dbt` (trust: this repo, branch `main`), repo secrets `AWS_ROLE_ARN` + `S3_BUCKET`, `aws-smoke-test.yml`.
- **Session 4:** Branch `feature/generator-contracts` (from `main` after PR #1 + PR #2). Added `faker` + `boto3`. First draft `generator/generate.py` (contracts only, never run) – **to be rewritten** to the new rules: Pythonic code with type hints + Google docstrings, independent per-table steps, full schema and dirty data from [docs/02-data-contract.md](docs/02-data-contract.md) (written this session; includes `INCLUDE_IN_STATS` Y/N, `<unknown>` sentinel, rejected-rows quarantine). `data/` added to `.gitignore`. **Next step:** rewrite the generator per the contract, run it locally, inspect the CSV, then `--upload` one day to S3.
- **Session 5:** Generator rewritten as a package per the contract: `generator/schema.py` (`TableSchema`), `contracts.py` (typed `Contract` dataclass, stable customer profiles, Decimal amounts), `dirty.py` (generic issue catalog, 1–3 issues per dirty row, duplicates), `storage.py` (CSV + S3), `generate.py` (CLI, each table isolated in try/except, exit code 0/1). Run: `uv run python -m generator.generate --table contracts --date 2026-10-10 --rows 20 --dirty-rate 0.3 --seed 42` – works locally, output reviewed and accepted. VS Code: interpreter = project `.venv`. First file in S3: `raw/contracts/dt=2026-10-10/contracts.csv` (4504 B, uploaded by the generator with `--upload --bucket leasing-dbt-radeq-2026`). **Next step:** catch-up / `--backfill N` mode (generate all missing days up to today), then extend to `customers`, `installment_schedule`, `payments`.
- **Session 6:** Moved to the Claude Code extension in VS Code. Git synced (local `main` = `origin/main` after PR #3), branch `feature/generator-backfill`. Done: pure function `missing_days()` in `generator/days.py` (written by me, spec = docstring + `tests/test_days.py`, 10 pytest tests – first tests in the project), `pytest` as a dev dependency – **PR #4 merged**. Also: Python learning track started (`learning/python/`, local only; modules 1–2 done, drill 01 ready), web research on best practices → [docs/03-engineering-guidelines.md](docs/03-engineering-guidelines.md). **Next step:** wire `missing_days()` into the generator – list existing `dt=` partitions in S3 (boto3), add `--backfill N` / `--catch-up` to `generate.py`, then run a real 90-day backfill.
- **Session 7 (2026-10-16):** PR #5 merged (engineering guidelines); local `main` synced, branch `feature/generator-catch-up`. Decided to start dbt early (see Decisions). Done: `parse_partition_day()` (pure, 9 pytest cases) and `list_existing_days()` (boto3 paginator) in `generator/storage.py`; `--catch-up`, `--backfill N`, `--dry-run` in `generate.py` (days planned per table via `missing_days()`, per-day seed `seed + day.toordinal()`, a failing day stops only its own table). Real run: 90 daily partitions of `contracts` in S3 (2026-07-19 .. 2026-10-16); a second run says "up to date" (idempotent). Daily use: `uv run python -m generator.generate --table contracts --catch-up --upload --bucket leasing-dbt-radeq-2026`. **Next step:** Stage 2 on `contracts` – `dbt init`, `dbt debug`, DuckDB reads from S3, source + staging model, first tests.
