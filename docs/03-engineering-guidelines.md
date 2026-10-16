# 03 – Engineering guidelines

Binding rules for all code in this repo, in priority order: **Python → pandas → data engineering**.
Each rule says what we do and, where it applies, how this project already follows it (✅) or what is still to do (⬜).

Researched in October 2026. Sources are listed at the end; most community sources are informal, so official docs (PEP 8, pandas docs, tool docs) win when they disagree.

---

## 1. Python

### Style and readability
- **PEP 8**, enforced mechanically with **ruff** (`ruff format` + `ruff check`) rather than by hand. ⬜ add ruff to dev dependencies and CI.
- **Type hints on every function** (arguments and return), using built-in generics: `list[str]`, `dict[str, int]`, `X | None`. ✅
- **Docstrings on every module, class and function**, Google style (`Args:`, `Returns:`, `Raises:`). ✅
- **Named constants** (UPPER_CASE, module level) instead of magic numbers. ✅
- **Small, single-purpose, preferably pure functions** (no hidden I/O, clock or randomness – pass them in as arguments, e.g. `today`, `rng`). ✅ (`missing_days()`, seeded `rng`)
- **No dead code** (unused variables, commented-out blocks) in commits.
- **`logging`, not `print`.** ✅

### Errors
- Raise **specific exceptions** (`TypeError` for wrong types, `ValueError` for wrong values) with a message that shows the bad value. ✅
- Catch broad `Exception` only at a **process boundary** (e.g. one table step in `generate.py`), log it with `logger.exception`, and keep going. ✅

### Project and tooling
- **uv** for Python versions, virtual environments and dependencies; `pyproject.toml` + `uv.lock` committed. ✅
- **All tool config in `pyproject.toml`** (pytest, ruff, type checker). ✅ pytest, ⬜ ruff, ⬜ type checker.
- **pytest** for all tests; prefer `@pytest.mark.parametrize` and fixtures. ✅
- **Static type checking** (mypy or ty) in CI. ⬜ later.
- Optional: `src/` layout for libraries. We keep the flat `generator/` package (an application, not a published library) – a deliberate choice.

---

## 2. pandas (when we start using it – learning modules 11–12, Stage 5)

We target **pandas 3.x** (released January 2026; requires Python ≥ 3.11).

- **Copy-on-Write is always on.** Every indexing result behaves like a copy, so chained assignment (`df["a"][0] = 5`) silently does nothing. Always write through **one `.loc`**: `df.loc[row, "a"] = 5`. No defensive `.copy()` calls needed.
- **Strings are the `str` dtype**, not `object`. Check string columns with `pd.api.types.is_string_dtype`, never `dtype == object`. Install **pyarrow** alongside pandas for fast string handling.
- **Read raw data as text, cast explicitly.** `pd.read_csv(path, dtype=str)` on the raw layer, then cast column by column – the same "all-varchar raw" rule as our data contract.
- **Vectorize; don't loop over rows.** Avoid `iterrows()` / row-wise `apply()` – use column operations, `.str`, `.dt`, `np.where`, `pd.cut`.
- **Method chaining** with `assign`, `query`, `pipe` (and `pd.col(...)` expressions in pandas 3) for readable step-by-step transformations – one step per line, like tools on an Alteryx canvas.
- **Dates:** parse explicitly (`pd.to_datetime(..., format=...)`); pandas 3 infers microsecond resolution – don't cast datetimes to `int64`.
- **Use DuckDB / polars when they fit better** (SQL on files, larger-than-memory data) – pandas is one tool, not the default for everything.

---

## 3. Data engineering

### Pipeline design
- **Separate ingestion from transformation.** Land raw data unchanged, apply business logic afterwards (dbt). ✅ raw CSV in S3 → dbt.
- **Single-purpose, independent stages** with explicit inputs/outputs (S3 / files); one failing stage doesn't stop unrelated ones. ✅ per-table steps.
- **Partition by time.** ✅ `dt=YYYY-MM-DD` Hive partitions – enables incremental loads, pruning and backfills.

### Reliability
- **Idempotency:** re-running a job for the same day gives the same result. We **overwrite the whole partition** (same key, deterministic seed), never blindly append. ✅ generator; ⬜ keep it true for dbt incremental models (use `merge` / `delete+insert`, not plain `append`).
- **Backfill and catch-up** as first-class modes. ✅ `--catch-up`, `--backfill N`, `--dry-run` (plan first, then run).
- **Retries with backoff** for transient errors (boto3 retries S3 calls by default; orchestrator retries for whole steps).
- **Design for failure:** decide per failure whether to retry, skip and log, alert or halt; report via exit codes. ✅ exit code 0/1.

### Data quality and contracts
- **Data contract at the boundary:** column names, types, nullability, allowed values. ✅ [docs/02-data-contract.md](02-data-contract.md).
- **Validate on ingestion and again before serving** (dbt tests in staging and marts). ⬜ Stage 2–3.
- **Never let the reader guess the file format.** Set CSV `delim`, `quote`, `escape`, `header` and column types explicitly. Auto-detection samples a few files and applies the result to all of them; when the guess is wrong the failure is *silent*. ✅ Real case: reading 90 daily files with a glob, DuckDB guessed "no quote character", split the quoted value `"12,5O"` into two fields and shifted the rest of that row by one column (`status` held a region name). No error was raised; only an `accepted_values` test on `status` exposed it. Fix: explicit dialect in `sources.yml`.
- **Quarantine, don't drop:** invalid rows go to a `__rejected` table with the reason. ✅ designed in the contract.
- **Test keys for nulls and uniqueness** – the highest-value tests. ⬜ Stage 2.
- **Track quality over time:** row counts vs. a baseline, null and duplicate rates. ⬜ later.

### Schema management
- **Treat the schema as an API:** additive changes are free; renames/removals are announced and versioned (contract v1, v2, …). ✅ contract is versioned.
- **Document every column** (dbt `schema.yml` descriptions). ⬜ Stage 2.

### Observability
- **Freshness per table** (dbt source freshness on `dt`). ⬜ Stage 2.
- **Structured logs** with pipeline, step, day, row count, status. ⬜ upgrade `generate.py` logging.
- **Lineage** via dbt docs. ⬜ Stage 2.

### Security and cost
- **No secrets in the repo;** credentials from the default chain (local profile, OIDC role in CI). ✅
- **Least privilege** IAM, private buckets, budget alerts. ✅

---

## Sources

- [pandas 3.0.0 – What's new (official)](https://pandas.pydata.org/docs/whatsnew/v3.0.0.html)
- [pandas 3.0 released (official blog)](https://pandas.pydata.org/community/blog/pandas-3.0.html)
- [What's new in pandas 3.0 – CodeCut](https://codecut.ai/pandas-3-whats-new/)
- [Data Engineering Best Practices: The Complete Checklist – Data Lakehouse Hub](https://datalakehousehub.com/blog/2026-02-de-best-practices-10-checklist)
- [Idempotent Pipelines – Data Lakehouse Hub](https://datalakehousehub.com/blog/2026-02-de-best-practices-04-idempotent-pipelines)
- [What maintainers look for in a Python project – dasroot.net](https://dasroot.net/posts/2026/03/what-maintainers-look-for-python-project/)
- [Data Engineer Roadmap 2026 – Analytics Vidhya](https://www.analyticsvidhya.com/blog/2026/01/data-engineer-roadmap/)
- [Junior Data Engineer guide – ResumeGeni](https://resumegeni.com/blog/data-engineer/junior)
- Official: [PEP 8](https://peps.python.org/pep-0008/), [ruff docs](https://docs.astral.sh/ruff/), [uv docs](https://docs.astral.sh/uv/)
