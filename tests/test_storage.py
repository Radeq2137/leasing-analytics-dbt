"""Tests for the pure helpers in generator.storage (no AWS involved)."""

from datetime import date

import pytest

from generator.storage import parse_partition_day


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("raw/contracts/dt=2026-10-10/contracts.csv", date(2026, 10, 10)),
        ("raw/payments/dt=2026-01-01/payments.csv", date(2026, 1, 1)),
        ("dt=2026-10-10/contracts.csv", date(2026, 10, 10)),
    ],
)
def test_parse_partition_day_returns_the_date(key: str, expected: date) -> None:
    assert parse_partition_day(key) == expected


@pytest.mark.parametrize(
    "key",
    [
        "raw/contracts/",  # folder placeholder, no partition
        "raw/contracts/contracts.csv",  # no dt= part
        "raw/contracts/dt=2026-13-45/contracts.csv",  # not a real date
        "raw/contracts/dt=yesterday/contracts.csv",  # not a date at all
        "raw/contracts/dt=/contracts.csv",  # empty value
        "",
    ],
)
def test_parse_partition_day_returns_none_when_there_is_no_valid_day(key: str) -> None:
    assert parse_partition_day(key) is None
