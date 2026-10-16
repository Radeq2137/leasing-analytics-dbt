"""Tests for registration_date_of: the inverse of customer_numbers_for_day (pure, no AWS)."""

from datetime import date, timedelta

import pytest

from generator.customers import GO_LIVE_DATE, customer_numbers_for_day, registration_date_of


@pytest.mark.parametrize(
    ("customer_no", "expected"),
    [
        (1, date(2026, 7, 19)),  # first customer: the initial batch registers on go-live
        (150, date(2026, 7, 19)),  # last customer of the initial batch
        (151, date(2026, 7, 20)),  # first customer of the first day after go-live
        (153, date(2026, 7, 20)),  # last customer of that day
        (154, date(2026, 7, 21)),  # first customer of the next day
        (156, date(2026, 7, 21)),
        (417, date(2026, 10, 16)),  # last customer of our 90-day backfill (150 + 3 * 89)
    ],
)
def test_registration_date_of(customer_no: int, expected: date) -> None:
    assert registration_date_of(customer_no) == expected


@pytest.mark.parametrize("customer_no", [0, -1, -150])
def test_registration_date_of_rejects_numbers_below_one(customer_no: int) -> None:
    with pytest.raises(ValueError, match=str(customer_no)):
        registration_date_of(customer_no)


def test_registration_date_of_agrees_with_customer_numbers_for_day() -> None:
    """Every number that registers on a day must map back to exactly that day (60 days in a row)."""
    for offset in range(60):
        day = GO_LIVE_DATE + timedelta(days=offset)
        for customer_no in customer_numbers_for_day(day):
            assert registration_date_of(customer_no) == day
