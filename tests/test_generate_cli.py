"""Tests for the generator CLI: argument rules and day planning (S3 is replaced by a stub)."""

from datetime import date, timedelta

import pytest

from generator import generate

BASE = ["--catch-up", "--upload", "--bucket", "test-bucket"]


def test_both_tables_are_registered() -> None:
    assert set(generate.TABLES) == {"customers", "contracts"}


def test_backfill_from_is_accepted_with_catch_up() -> None:
    args = generate.parse_args([*BASE, "--backfill-from", "2026-07-19"])
    assert args.backfill_from == date(2026, 7, 19)
    assert args.backfill is None


def test_backfill_and_backfill_from_exclude_each_other() -> None:
    with pytest.raises(SystemExit):
        generate.parse_args([*BASE, "--backfill", "5", "--backfill-from", "2026-07-19"])


@pytest.mark.parametrize("option", [["--backfill", "5"], ["--backfill-from", "2026-07-19"]])
def test_backfill_options_need_catch_up(option: list[str]) -> None:
    with pytest.raises(SystemExit):
        generate.parse_args(["--upload", "--bucket", "test-bucket", *option])


def test_backfill_from_must_not_be_in_the_future() -> None:
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    with pytest.raises(SystemExit):
        generate.parse_args([*BASE, "--backfill-from", tomorrow])


def test_backfill_from_plans_every_day_from_that_date_to_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generate, "list_existing_days", lambda bucket, table: set())
    today = date.today()
    start = today - timedelta(days=2)
    args = generate.parse_args([*BASE, "--backfill-from", start.isoformat()])
    assert generate.days_to_generate("customers", args) == [start, start + timedelta(days=1), today]


def test_backfill_from_is_ignored_when_the_table_already_has_data(monkeypatch: pytest.MonkeyPatch) -> None:
    today = date.today()
    monkeypatch.setattr(generate, "list_existing_days", lambda bucket, table: {today - timedelta(days=1)})
    args = generate.parse_args([*BASE, "--backfill-from", (today - timedelta(days=30)).isoformat()])
    assert generate.days_to_generate("customers", args) == [today]  # catch-up wins over backfill
