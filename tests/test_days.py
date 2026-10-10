"""Tests for generator.days.missing_days – the specification of catch-up and backfill."""

from datetime import date

import pytest

from generator.days import missing_days

TODAY = date(2026, 10, 13)


def test_catch_up_returns_days_after_latest_existing_day() -> None:
    existing = {date(2026, 10, 9), date(2026, 10, 10)}

    assert missing_days(existing, TODAY) == [
        date(2026, 10, 11),
        date(2026, 10, 12),
        date(2026, 10, 13),
    ]


def test_catch_up_returns_nothing_when_up_to_date() -> None:
    assert missing_days({TODAY}, TODAY) == []


def test_catch_up_returns_nothing_when_latest_day_is_in_the_future() -> None:
    assert missing_days({date(2026, 10, 20)}, TODAY) == []


def test_catch_up_does_not_fill_gaps_before_latest_day() -> None:
    existing = {date(2026, 10, 1), date(2026, 10, 12)}

    assert missing_days(existing, TODAY) == [TODAY]


def test_catch_up_ignores_backfill_when_partitions_exist() -> None:
    assert missing_days({date(2026, 10, 12)}, TODAY, backfill_days=90) == [TODAY]


def test_backfill_returns_last_n_days_ending_today() -> None:
    assert missing_days(set(), TODAY, backfill_days=3) == [
        date(2026, 10, 11),
        date(2026, 10, 12),
        date(2026, 10, 13),
    ]


def test_backfill_of_90_days_starts_89_days_before_today() -> None:
    days = missing_days(set(), TODAY, backfill_days=90)

    assert len(days) == 90
    assert days[0] == date(2026, 7, 16)
    assert days[-1] == TODAY


def test_first_run_without_backfill_returns_only_today() -> None:
    assert missing_days(set(), TODAY) == [TODAY]


@pytest.mark.parametrize("backfill_days", [0, -5])
def test_backfill_smaller_than_one_raises(backfill_days: int) -> None:
    with pytest.raises(ValueError):
        missing_days(set(), TODAY, backfill_days=backfill_days)
