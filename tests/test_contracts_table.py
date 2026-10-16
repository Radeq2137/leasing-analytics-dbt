"""Tests for the raw ``contracts`` table: customers, delivery address and orphans (no AWS)."""

import random
from collections import Counter
from datetime import date, timedelta

import pytest

from generator.contracts import ORPHAN_CUSTOMER_NOS, SCHEMA, build_raw_rows, orphan_customer_id
from generator.customers import GO_LIVE_DATE, registered_count, registration_date_of
from generator.reference import cities_by_region

SEED = 42
ROWS_PER_DAY = 20
SAMPLE_DAYS = [GO_LIVE_DATE + timedelta(days=offset) for offset in (0, 1, 2, 10, 45, 89)]


def _customer_no(customer_id: str) -> int:
    """Turn ``CU-00151`` into 151."""
    return int(customer_id.removeprefix("CU-"))


def test_no_contracts_before_go_live() -> None:
    rows, issues = build_raw_rows(GO_LIVE_DATE - timedelta(days=1), ROWS_PER_DAY, 0.5, SEED)
    assert rows == []
    assert not issues


@pytest.mark.parametrize("day", SAMPLE_DAYS)
def test_clean_contracts_reference_only_customers_already_registered(day: date) -> None:
    rows, _ = build_raw_rows(day, ROWS_PER_DAY, 0.0, SEED)
    assert len(rows) == ROWS_PER_DAY
    for row in rows:
        customer_no = _customer_no(row["customer_id"])
        assert 1 <= customer_no <= registered_count(day)
        assert registration_date_of(customer_no) <= day


@pytest.mark.parametrize("day", SAMPLE_DAYS)
def test_clean_delivery_city_belongs_to_the_region(day: date) -> None:
    rows, _ = build_raw_rows(day, ROWS_PER_DAY, 0.0, SEED)
    regions = cities_by_region()
    for row in rows:
        city, region = row["delivery_city"], row["delivery_region"]
        if city and region:  # an optional field may be blank, and a blank never counts as a mismatch
            assert city in regions[region]


def test_orphan_customer_id_points_to_a_customer_that_never_registers() -> None:
    row = {"customer_id": "CU-00010"}
    assert orphan_customer_id(row, SCHEMA, random.Random(1), GO_LIVE_DATE) is True
    low, high = ORPHAN_CUSTOMER_NOS
    assert low <= _customer_no(row["customer_id"]) <= high


def test_orphan_customer_id_skips_a_blank_customer_id() -> None:
    row = {"customer_id": ""}
    assert orphan_customer_id(row, SCHEMA, random.Random(1), GO_LIVE_DATE) is False
    assert row["customer_id"] == ""


def test_dirty_run_injects_orphans() -> None:
    issues: Counter[str] = Counter()
    for day in SAMPLE_DAYS:
        issues.update(build_raw_rows(day, ROWS_PER_DAY, 1.0, SEED)[1])
    assert issues["orphan_customer_id"] > 0


def test_same_day_and_seed_give_the_same_rows() -> None:
    day = GO_LIVE_DATE + timedelta(days=5)
    assert build_raw_rows(day, ROWS_PER_DAY, 0.3, SEED) == build_raw_rows(day, ROWS_PER_DAY, 0.3, SEED)


def test_rows_have_exactly_the_contract_columns() -> None:
    rows, _ = build_raw_rows(GO_LIVE_DATE, ROWS_PER_DAY, 0.5, SEED)
    assert all(tuple(row) == SCHEMA.columns for row in rows)


def test_negative_row_count_is_rejected() -> None:
    with pytest.raises(ValueError, match="-1"):
        build_raw_rows(GO_LIVE_DATE, -1, 0.0, SEED)
