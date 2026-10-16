"""Tests for the customer timeline in generator.customers (pure functions, no AWS)."""

from datetime import date, timedelta

import pytest

from generator.customers import (
    GO_LIVE_DATE,
    INITIAL_CUSTOMERS,
    NEW_CUSTOMERS_PER_DAY,
    customer_numbers_for_day,
    registered_count,
)


def test_constants_match_the_data_contract() -> None:
    assert GO_LIVE_DATE == date(2026, 7, 19)
    assert INITIAL_CUSTOMERS == 150
    assert NEW_CUSTOMERS_PER_DAY == 3


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 7, 18), 0),  # the day before go-live: nobody is registered yet
        (date(2020, 1, 1), 0),  # long before go-live
        (date(2026, 7, 19), 150),  # go-live: the initial batch
        (date(2026, 7, 20), 153),  # +1 day: 3 new customers
        (date(2026, 7, 29), 180),  # +10 days
        (date(2026, 10, 16), 150 + 3 * 89),  # the last day of our 90-day backfill
    ],
)
def test_registered_count(day: date, expected: int) -> None:
    assert registered_count(day) == expected


def test_customer_numbers_before_go_live_is_empty() -> None:
    assert list(customer_numbers_for_day(date(2026, 7, 18))) == []


def test_customer_numbers_on_go_live_is_the_initial_batch() -> None:
    numbers = list(customer_numbers_for_day(GO_LIVE_DATE))
    assert len(numbers) == 150
    assert numbers[0] == 1
    assert numbers[-1] == 150


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 7, 20), [151, 152, 153]),
        (date(2026, 7, 21), [154, 155, 156]),
    ],
)
def test_customer_numbers_after_go_live(day: date, expected: list[int]) -> None:
    assert list(customer_numbers_for_day(day)) == expected


def test_days_in_a_row_leave_no_gaps_and_no_duplicates() -> None:
    """Joining the numbers of consecutive days gives exactly 1..registered_count(last day)."""
    all_numbers: list[int] = []
    last_day = GO_LIVE_DATE
    for offset in range(-5, 40):  # starts before go-live on purpose
        last_day = GO_LIVE_DATE + timedelta(days=offset)
        all_numbers.extend(customer_numbers_for_day(last_day))

    assert all_numbers == list(range(1, registered_count(last_day) + 1))
