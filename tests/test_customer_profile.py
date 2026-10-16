"""Tests for the customer profile: what must be true for CLEAN customers (no AWS, reads the seed)."""

import re
from datetime import date

import pytest

from generator.customers import (
    COLUMNS,
    CUSTOMER_TYPE_WEIGHTS,
    INDUSTRIES,
    PRIVATE_INDUSTRY,
    customer_profile,
    registration_date_of,
)
from generator.reference import load_city_region

# The customers of our 90-day backfill (150 + 3 * 89 = 417 customers).
ALL_NUMBERS = range(1, 418)
EMAIL_FORMAT = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]+$")


def test_profile_is_the_same_every_time() -> None:
    assert customer_profile(42) == customer_profile(42)
    assert customer_profile(42) != customer_profile(43)


def test_profile_id_and_registration_date() -> None:
    profile = customer_profile(151)
    assert profile.customer_id == "CU-00151"
    assert profile.registration_date == registration_date_of(151) == date(2026, 7, 20)


def test_customer_type_is_one_of_the_allowed_types() -> None:
    types = {customer_profile(n).customer_type for n in ALL_NUMBERS}
    assert types == set(CUSTOMER_TYPE_WEIGHTS)  # all three types occur


def test_industry_matches_the_customer_type() -> None:
    for n in ALL_NUMBERS:
        profile = customer_profile(n)
        if profile.customer_type == "individual":
            assert profile.industry == PRIVATE_INDUSTRY
        else:
            assert profile.industry in INDUSTRIES


def test_city_always_belongs_to_the_region() -> None:
    cities_by_region = load_city_region()
    for n in ALL_NUMBERS:
        profile = customer_profile(n)
        assert profile.city in cities_by_region[profile.region]


def test_clean_emails_are_valid_and_unique() -> None:
    emails = [customer_profile(n).customer_email for n in ALL_NUMBERS]
    assert all(EMAIL_FORMAT.match(email) for email in emails)
    assert len(emails) == len(set(email.lower() for email in emails))


def test_names_are_not_blank() -> None:
    assert all(customer_profile(n).customer_name.strip() for n in ALL_NUMBERS)


def test_raw_row_has_exactly_the_contract_columns_as_text() -> None:
    row = customer_profile(7).to_raw_row()
    assert tuple(row) == COLUMNS
    assert all(isinstance(value, str) for value in row.values())
    assert row["registration_date"] == "2026-07-19"


def test_profile_rejects_numbers_below_one() -> None:
    with pytest.raises(ValueError, match="0"):
        customer_profile(0)
