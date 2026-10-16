# 02 – Data contract: raw layer

This document defines what the generator writes to the raw layer and how dbt must treat it.
It is the single source of truth for column names, types, mandatory fields and data-quality rules.

Status: **draft v1 – `contracts` and `customers` tables**. Other tables (`installment_schedule`, `payments`) will be added as they are built.

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

## 3. Table `customers`

One row = one customer registered on business day `dt`.

### Incremental extract

The extract is **incremental**: the file of day `dt` contains **only the customers registered that day**
(`registration_date` = `dt`), never a full copy of the customer base. With a realistic base of hundreds of
thousands of customers, re-writing everything every day would be wasteful; downstream, dbt appends only the new
rows (incremental model, Stage 4).

- The project's **go-live date** is `2026-07-19` (first day of data). On that day an initial batch of
  `INITIAL_CUSTOMERS = 150` customers is registered; every following day `NEW_CUSTOMERS_PER_DAY = 3` new ones.
- Customer numbers are sequential in registration order and deterministic: day *k* after go-live (k ≥ 1) registers
  numbers `150 + 3*(k-1) + 1` … `150 + 3*k`. So `customer_id` is unique across the whole history.

| column | type (after staging) | mandatory | allowed values / format | notes |
|---|---|---|---|---|
| `customer_id` | text | ✅ | `CU-NNNNN` | business key, must be unique across all days |
| `customer_type` | text | ✅ | `company`, `sole_trader`, `individual` | case-insensitive in raw |
| `customer_name` | text | ✅ | free text | company name or full name (synthetic, Faker) |
| `industry` | text | ✅ | `transport`, `construction`, `manufacturing`, `retail`, `healthcare`, `it_services`, `agriculture`, `private` | case-insensitive in raw; `private` for individuals |
| `region` | text | ✅ | Polish voivodeship name | same list as `contracts.delivery_region` |
| `city` | text | ❌ | | |
| `customer_email` | text | ❌ | valid e-mail format | same value as in `contracts`; invalid format → warn |
| `registration_date` | date | ✅ | `YYYY-MM-DD`, ≤ `dt` | later than `dt` → rejected |

Row-level rules follow the general rules of section 1 (blank mandatory → rejected, `<unknown>` in mandatory text →
`unknown`, non-parsable date → rejected, duplicates of `customer_id` → quarantine `duplicate_customer_id`).

### Dirty data injected by the generator (`customers`)

| issue | example | expected handling |
|---|---|---|
| blank mandatory field | `customer_type = ''` | rejected, test `error` |
| `<unknown>` in mandatory text | `industry = '<unknown>'` | valid → `unknown` |
| inconsistent casing / whitespace | `' TRANSPORT'`, `Company` | normalized in staging, valid |
| invalid e-mail | `jan.kowalski@` | kept, test `warn` |
| duplicate `customer_id` | same id twice | quarantine `duplicate_customer_id`, test `unique` → `error` |
| future `registration_date` | `registration_date > dt` | rejected, test `error` |
| **duplicate e-mail** across different customers | two `customer_id`s with the same `customer_email` | **flagged, not rejected** (see below) |

### Duplicate e-mails (possible duplicate customers)

The same e-mail under two different `customer_id`s often means one customer registered twice, but a shared company
mailbox is also possible, so the row is **kept**. Because the second customer may register on a later day, this can
only be detected on the **combined table of all days** (`stg_customers`), never in a single daily file.

- Staging adds a boolean column `has_duplicate_email` (true when the same non-blank e-mail, compared case-insensitively
  and trimmed, belongs to more than one `customer_id`). Blank e-mails never count as duplicates.
- A dbt test on `customer_email` (`unique` over non-null values, severity `warn`) reports how many there are.
- Business decides later what to do with the flagged rows (e.g. merge in a customer dimension); the pipeline never drops them.
- The generator injects the issue by giving a small share of new customers the e-mail of an already registered one.

---

## 4. Cross-table rules

| rule | clean data | dirty data / handling |
|---|---|---|
| every `contracts.customer_id` exists in `customers` | always true | a small share of contracts get an **orphan** `customer_id` (no such customer) → dbt test `relationships` → `error`. Orphans are excluded from facts and listed in a quarantine model in the intermediate layer (Stage 3) |
| a contract is signed **on or after** the customer's `registration_date` | always true: the generator picks customers only among those already registered on `signed_date` | not injected |
| `customer_type` and `customer_email` in `contracts` equal those in `customers` (the contract extract repeats them) | always true (same profile source) | singular test (Stage 3), severity `warn` |

---

## 5. Dirty data injected by the generator (`contracts`)

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
| orphan `customer_id` | `CU-09999` (no such customer) | kept in staging; test `relationships` → `error`; excluded later (section 4) |

All data is synthetic. E-mails use reserved example domains (`example.com`, `example.pl`), addresses are generated by Faker (`pl_PL`).
