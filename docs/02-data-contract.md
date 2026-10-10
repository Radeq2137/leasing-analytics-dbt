# 02 – Data contract: raw layer

This document defines what the generator writes to the raw layer and how dbt must treat it.
It is the single source of truth for column names, types, mandatory fields and data-quality rules.

Status: **draft v1 – `contracts` table**. Other tables (`customers`, `installment_schedule`, `payments`) will be added as they are built.

---

## 1. General rules

### File layout

```
s3://<bucket>/raw/<table>/dt=YYYY-MM-DD/<table>.csv
```

- CSV, UTF-8, comma-separated, header row, one file per table per business day.
- `dt` is the Hive-style partition = the business date the file was generated for.

### Reading raw files

- dbt / DuckDB reads **every raw column as text** (`all_varchar=true`).
  Type inference is disabled on purpose: a single bad value (e.g. `<unknown>` in a numeric column) must never break the read of a whole table.
- Types are cast **only in staging**, with `try_cast`, so a bad value becomes a flagged row, not a failed pipeline.

### Mandatory vs optional, and the `<unknown>` sentinel

The source system lets users type `<unknown>` instead of leaving a field blank.

| column kind | value | verdict | staging behaviour |
|---|---|---|---|
| mandatory, text | non-empty value | ✅ valid | trimmed, normalized |
| mandatory, text | `<unknown>` | ✅ valid ("known unknown") | mapped to `unknown` |
| mandatory, any type | blank | ❌ invalid | row rejected (reason: `missing_mandatory_<column>`) |
| optional, text | blank or `<unknown>` | ✅ valid | mapped to `NULL` |
| numeric / date (mandatory or optional) | `<unknown>` or any non-parsable text | ❌ invalid | `try_cast` → `NULL`, row rejected (reason: `invalid_<type>_<column>`) |

### Valid vs rejected rows

- Each staging model splits its source into:
  - `stg_<table>` – rows that pass all row-level rules,
  - `stg_<table>__rejected` – rows that fail, with a `rejection_reason` column (quarantine).
- Rejected rows never stop the pipeline; dbt tests report them (`warn` or `error` severity, see below).
- Independence: a failure in one table never blocks other tables. Downstream models work on the last good data.

---

## 2. Table `contracts`

One row = one lease contract signed on business day `dt`.

| column | type (after staging) | mandatory | allowed values / format | notes |
|---|---|---|---|---|
| `transaction_id` | uuid | ✅ | UUID v4 | unique per row in the source extract |
| `contract_id` | text | ✅ | `CT-YYYYMMDD-NNNN` | business key, must be unique |
| `customer_id` | text | ✅ | `CU-NNNNN` | |
| `customer_type` | text | ✅ | `company`, `sole_trader`, `individual` | case-insensitive in raw |
| `customer_email` | text | ❌ | valid e-mail format | invalid format → warn |
| `vendor_id` | text | ✅ | `VN-NNNN` | |
| `vendor_type` | text | ✅ | `dealer`, `manufacturer`, `broker` | case-insensitive in raw |
| `asset_type` | text | ✅ | `car`, `truck`, `machinery`, `it_equipment`, `medical_equipment` | case-insensitive in raw |
| `asset_price` | decimal(18,2) | ✅ | > 0 | gross price of the leased asset, PLN |
| `net_value` | decimal(18,2) | ✅ | > 0, ≤ `asset_price` | financed net amount, PLN |
| `down_payment_pct` | decimal(5,2) | ❌ | 0–100 | |
| `term_months` | integer | ✅ | 12–84 | |
| `signed_date` | date | ✅ | `YYYY-MM-DD`, ≤ `dt` | future date → rejected |
| `delivery_street` | text | ❌ | | where the asset is delivered |
| `delivery_city` | text | ❌ | | |
| `delivery_postal_code` | text | ❌ | `NN-NNN` | |
| `delivery_region` | text | ❌ | Polish voivodeship name | |
| `status` | text | ✅ | `active`, `closed`, `collections`, `terminated` | case-insensitive in raw |
| `INCLUDE_IN_STATS` | boolean | ✅ | `Y`, `N` | see below |

### `INCLUDE_IN_STATS`

Business decides which transactions go into reports. The column comes from a legacy part of the source system, hence the upper-case name.

- Staging renames it to `include_in_stats` (snake_case, like every other column) and casts it to boolean: `Y` → `true`, `N` → `false` (case-insensitive, trimmed).
- `<unknown>` is accepted (mandatory text rule) and becomes `NULL`. Such rows are **excluded from reporting** – only an explicit `Y` goes into the marts' statistics.
- Blank → rejected (`missing_mandatory_include_in_stats`).
- Any other value (`yes`, `1`, `X`, …) → rejected (`invalid_value_include_in_stats`).

---

## 3. Dirty data injected by the generator

The generator injects these issues with a configurable probability (`--dirty-rate`) so the dbt layer has something to catch.

| issue | example | expected handling |
|---|---|---|
| blank mandatory field | `customer_type = ''` | rejected, test `error` |
| `<unknown>` in mandatory text | `vendor_type = '<unknown>'` | valid → `unknown` |
| `<unknown>` in numeric field | `asset_price = '<unknown>'` | rejected, test `error` |
| non-numeric text in numeric field | `term_months = 'abc'` | rejected, test `error` |
| negative / zero amount | `net_value = -1500.00` | rejected, test `error` |
| `net_value` > `asset_price` | | rejected, test `warn` |
| future `signed_date` | `signed_date > dt` | rejected, test `error` |
| duplicate `contract_id` | same id twice in a day or across days | test `unique` → `error` |
| inconsistent casing / whitespace | `' Active'`, `CAR` | normalized in staging, valid |
| invalid e-mail | `jan.kowalski@` | kept, test `warn` |
| invalid `INCLUDE_IN_STATS` | `yes`, `1` | rejected, test `error` |

All data is synthetic. E-mails use reserved example domains (`example.com`, `example.pl`), addresses are generated by Faker (`pl_PL`).
