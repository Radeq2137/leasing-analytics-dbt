"""Tests for the raw ``customers`` table: rows per day and the injected dirty data (no AWS)."""

import random
from collections import Counter
from datetime import date, timedelta

from generator.customers import (
    COLUMNS,
    GO_LIVE_DATE,
    SCHEMA,
    build_raw_rows,
    city_region_mismatch,
    customer_numbers_for_day,
    customer_profile,
    duplicate_email,
    registered_count,
)
from generator.reference import load_city_region

SEED = 42


def test_clean_rows_are_the_profiles_of_the_customers_registering_that_day() -> None:
    day = date(2026, 7, 21)
    rows, issues = build_raw_rows(day, 0, 0.0, SEED)
    assert rows == [customer_profile(n).to_raw_row() for n in customer_numbers_for_day(day)]
    assert not issues


def test_number_of_rows_follows_the_timeline_not_n_rows() -> None:
    assert build_raw_rows(GO_LIVE_DATE - timedelta(days=1), 99, 0.0, SEED)[0] == []
    assert len(build_raw_rows(GO_LIVE_DATE, 99, 0.0, SEED)[0]) == 150
    assert len(build_raw_rows(GO_LIVE_DATE + timedelta(days=1), 99, 0.0, SEED)[0]) == 3


def test_every_row_has_exactly_the_contract_columns() -> None:
    rows, _ = build_raw_rows(date(2026, 7, 25), 0, 1.0, SEED)
    assert SCHEMA.columns == COLUMNS
    assert all(tuple(row) == COLUMNS for row in rows)


def test_same_day_and_seed_give_the_same_rows() -> None:
    day = date(2026, 8, 3)
    assert build_raw_rows(day, 0, 0.5, SEED) == build_raw_rows(day, 0, 0.5, SEED)


def test_duplicate_email_reuses_the_email_of_an_earlier_customer() -> None:
    day = date(2026, 7, 25)
    row = customer_profile(registered_count(day)).to_raw_row()  # a customer registering on ``day``
    assert duplicate_email(row, SCHEMA, random.Random(1), day) is True
    earlier_emails = {customer_profile(n).customer_email for n in range(1, registered_count(day - timedelta(days=1)) + 1)}
    assert row["customer_email"] in earlier_emails


def test_duplicate_email_is_impossible_on_go_live() -> None:
    row = customer_profile(1).to_raw_row()
    assert duplicate_email(row, SCHEMA, random.Random(1), GO_LIVE_DATE) is False  # nobody registered before


def test_city_region_mismatch_picks_a_city_of_another_region() -> None:
    cities_by_region = load_city_region()
    row = customer_profile(10).to_raw_row()
    region = row["region"]
    assert city_region_mismatch(row, SCHEMA, random.Random(1), GO_LIVE_DATE) is True
    assert row["region"] == region  # only the city changes
    assert row["city"] not in cities_by_region[region]


def test_city_region_mismatch_ignores_a_blank_region() -> None:
    row = customer_profile(10).to_raw_row()
    row["region"] = ""
    assert city_region_mismatch(row, SCHEMA, random.Random(1), GO_LIVE_DATE) is False


def test_dirty_run_injects_the_customer_issues() -> None:
    issues: Counter[str] = Counter()
    for offset in range(1, 41):
        issues.update(build_raw_rows(GO_LIVE_DATE + timedelta(days=offset), 0, 1.0, SEED)[1])
    assert issues["duplicate_email"] > 0
    assert issues["city_region_mismatch"] > 0
    assert issues["duplicate_business_key"] > 0
    assert issues["blank_mandatory"] > 0
