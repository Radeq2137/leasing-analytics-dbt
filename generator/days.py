"""Selection of the business days the generator still has to produce."""

from datetime import date, timedelta


def missing_days(existing: set[date], today: date, backfill_days: int | None = None) -> list[date]:
    """Return the business days that still have to be generated, oldest first.

    Rules:
        1. Catch-up: if ``existing`` is not empty, return every day after the
           latest existing day, up to and including ``today``. Gaps before the
           latest day are not filled. If the latest day is ``today`` or later,
           there is nothing to do.
        2. Backfill: if ``existing`` is empty and ``backfill_days`` is given,
           return the last ``backfill_days`` days ending with ``today``.
        3. First run without backfill: if ``existing`` is empty and
           ``backfill_days`` is None, return just ``today``.

    Args:
        existing: Days that already have a partition (``dt=``) for the table.
        today: Last day to generate (inclusive).
        backfill_days: How many days of history to create when ``existing``
            is empty. Ignored when ``existing`` is not empty.

    Returns:
        Days to generate, sorted from oldest to newest; empty if up to date.

    Raises:
        TypeError: If ``backfill_days`` is given and is not an int, or if
            ``existing`` is not a set.
        ValueError: If ``backfill_days`` is given and is smaller than 1.

    Examples:
        >>> missing_days({date(2026, 10, 10)}, today=date(2026, 10, 13))
        [datetime.date(2026, 10, 11), datetime.date(2026, 10, 12), datetime.date(2026, 10, 13)]
        >>> missing_days(set(), today=date(2026, 10, 13), backfill_days=3)
        [datetime.date(2026, 10, 11), datetime.date(2026, 10, 12), datetime.date(2026, 10, 13)]
    """
    # Validation: backfill_days, when given, must be an int of at least 1.
    if backfill_days is not None:
        # TypeError: backfill_days is not an int.
        if not isinstance(backfill_days, int):
            raise TypeError(f"backfill_days must be an int, got {type(backfill_days).__name__}")
        # ValueError: backfill_days is 0 or negative.
        if backfill_days < 1:
            raise ValueError(f"backfill_days must be >= 1, got {backfill_days}")

    # Validation: existing must be a set (an empty set is fine – no data yet).
    if not isinstance(existing, set):
        raise TypeError(f"existing must be a set of dates, got {type(existing).__name__}")

    # Situation 1 – catch-up: there is data already.
    if existing:
        last_day = max(existing)
        gap = (today - last_day).days
        return [last_day + timedelta(days=i) for i in range(1, gap + 1)]

    # Situation 2 – empty set + backfill: the last backfill_days days.
    if backfill_days is not None:
        first_day = today - timedelta(days=backfill_days - 1)
        return [first_day + timedelta(days=i) for i in range(backfill_days)]

    # Situation 3 – first run without backfill: only today.
    return [today]
