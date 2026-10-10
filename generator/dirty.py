"""Injection of intentionally dirty data into raw rows.

Every issue from the "Dirty data" catalog in docs/02-data-contract.md is a
small function that mutates one row in place. The functions only rely on a
``TableSchema``, so the same catalog works for every table.
"""

import random
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from generator.schema import Row, TableSchema

UNKNOWN = "<unknown>"
NON_NUMERIC_VALUES = ("abc", "n/a", "12,5O", "-")
INVALID_FLAG_VALUES = ("yes", "no", "1", "0", "X")
MAX_FUTURE_DAYS = 30
# A dirty row gets between 1 and this many distinct issues (real bad rows are
# rarely wrong in just one place).
MAX_ISSUES_PER_ROW = 3
# Share of dirty-rate draws that become a duplicated business key instead of
# a row-level issue (duplicates are rarer than typos).
DUPLICATE_SHARE = 0.2

IssueFn = Callable[[Row, TableSchema, random.Random, date], bool]
"""Mutates a row in place; returns False when the issue cannot be applied."""


def _pick_filled(rng: random.Random, row: Row, columns: Iterable[str]) -> str | None:
    """Pick a random column from ``columns`` that has a non-empty value.

    Args:
        rng: Seeded random generator.
        row: Row to look at.
        columns: Candidate column names.

    Returns:
        A column name, or None if no candidate has a value.
    """
    candidates = sorted(c for c in columns if row.get(c, "").strip())
    return rng.choice(candidates) if candidates else None


def parse_decimal(value: str) -> Decimal | None:
    """Parse text as a Decimal.

    Args:
        value: Raw text value.

    Returns:
        The parsed number, or None if the text is not a number.
    """
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def blank_mandatory(row: Row, schema: TableSchema, rng: random.Random, day: date) -> bool:
    """Blank out a mandatory column (invalid: row must be rejected)."""
    column = _pick_filled(rng, row, schema.mandatory)
    if column is None:
        return False
    row[column] = ""
    return True


def unknown_in_mandatory_text(row: Row, schema: TableSchema, rng: random.Random, day: date) -> bool:
    """Put ``<unknown>`` into a mandatory categorical/flag column (valid by contract)."""
    column = _pick_filled(rng, row, (schema.categorical | schema.flags) & schema.mandatory)
    if column is None:
        return False
    row[column] = UNKNOWN
    return True


def unknown_in_numeric(row: Row, schema: TableSchema, rng: random.Random, day: date) -> bool:
    """Put ``<unknown>`` into a numeric column (invalid: cannot be cast)."""
    column = _pick_filled(rng, row, schema.numeric)
    if column is None:
        return False
    row[column] = UNKNOWN
    return True


def text_in_numeric(row: Row, schema: TableSchema, rng: random.Random, day: date) -> bool:
    """Put non-numeric text into a numeric column (invalid: cannot be cast)."""
    column = _pick_filled(rng, row, schema.numeric)
    if column is None:
        return False
    row[column] = rng.choice(NON_NUMERIC_VALUES)
    return True


def negative_amount(row: Row, schema: TableSchema, rng: random.Random, day: date) -> bool:
    """Turn a positive amount negative (invalid: amounts must be > 0)."""
    column = _pick_filled(rng, row, schema.amounts)
    value = parse_decimal(row[column]) if column else None
    if column is None or value is None:
        return False
    row[column] = str(-abs(value))
    return True


def future_date(row: Row, schema: TableSchema, rng: random.Random, day: date) -> bool:
    """Move a date after the business day (invalid: future dates are rejected)."""
    column = _pick_filled(rng, row, schema.dates)
    if column is None:
        return False
    row[column] = (day + timedelta(days=rng.randint(1, MAX_FUTURE_DAYS))).isoformat()
    return True


def messy_casing(row: Row, schema: TableSchema, rng: random.Random, day: date) -> bool:
    """Change casing / add whitespace in a categorical column (valid after normalization)."""
    column = _pick_filled(rng, row, schema.categorical)
    if column is None:
        return False
    value = row[column]
    row[column] = rng.choice((value.upper(), value.title(), f" {value} "))
    return True


def invalid_email(row: Row, schema: TableSchema, rng: random.Random, day: date) -> bool:
    """Cut the domain off an e-mail address (kept, but reported as a warning)."""
    column = _pick_filled(rng, row, schema.emails)
    if column is None:
        return False
    row[column] = row[column].split("@")[0] + "@"
    return True


def invalid_flag(row: Row, schema: TableSchema, rng: random.Random, day: date) -> bool:
    """Put a value other than ``Y``/``N``/``<unknown>`` into a flag (invalid)."""
    column = _pick_filled(rng, row, schema.flags)
    if column is None:
        return False
    row[column] = rng.choice(INVALID_FLAG_VALUES)
    return True


ROW_ISSUES: dict[str, IssueFn] = {
    "blank_mandatory": blank_mandatory,
    "unknown_in_mandatory_text": unknown_in_mandatory_text,
    "unknown_in_numeric": unknown_in_numeric,
    "text_in_numeric": text_in_numeric,
    "negative_amount": negative_amount,
    "future_date": future_date,
    "messy_casing": messy_casing,
    "invalid_email": invalid_email,
    "invalid_flag": invalid_flag,
}


def _apply_random_issues(
    row: Row,
    schema: TableSchema,
    rng: random.Random,
    day: date,
    issues: Mapping[str, IssueFn],
    n_issues: int,
) -> list[str]:
    """Apply up to ``n_issues`` distinct, randomly chosen issues that fit the row.

    Args:
        row: Row to mutate in place.
        schema: Schema of the row's table.
        rng: Seeded random generator.
        day: Business day of the file.
        issues: Available issues, by name.
        n_issues: Maximum number of distinct issues to apply.

    Returns:
        Names of the applied issues (empty if none of them fits).
    """
    names = sorted(issues)
    rng.shuffle(names)
    applied: list[str] = []
    for name in names:
        if len(applied) == n_issues:
            break
        if issues[name](row, schema, rng, day):
            applied.append(name)
    return applied


def _duplicate(row: Row, schema: TableSchema, rng: random.Random) -> Row:
    """Copy a row, keeping its business key but giving it a new row id.

    Args:
        row: Row to copy.
        schema: Schema of the row's table.
        rng: Seeded random generator.

    Returns:
        A new row that duplicates ``row``'s business key.
    """
    copy = dict(row)
    if schema.row_id:
        copy[schema.row_id] = str(uuid.UUID(int=rng.getrandbits(128), version=4))
    return copy


def inject_dirty_data(
    rows: list[Row],
    schema: TableSchema,
    day: date,
    dirty_rate: float,
    rng: random.Random,
    extra_issues: Mapping[str, IssueFn] | None = None,
) -> tuple[list[Row], Counter[str]]:
    """Return a copy of ``rows`` with dirty data injected.

    Each row becomes dirty with probability ``dirty_rate`` and then gets
    1 to ``MAX_ISSUES_PER_ROW`` distinct random issues. Separately,
    a row may be duplicated (same business key) with probability
    ``dirty_rate * DUPLICATE_SHARE``.

    Args:
        rows: Clean raw rows. Not modified.
        schema: Schema of the rows' table.
        day: Business day of the file.
        dirty_rate: Probability (0-1) that a row gets an issue.
        rng: Seeded random generator.
        extra_issues: Table-specific issues added to the generic catalog.

    Returns:
        The new rows and a count of injected issues by name.

    Raises:
        ValueError: If ``dirty_rate`` is outside 0-1.
    """
    if not 0 <= dirty_rate <= 1:
        raise ValueError(f"dirty_rate must be between 0 and 1, got {dirty_rate}")

    issues = {**ROW_ISSUES, **(extra_issues or {})}
    result: list[Row] = []
    counts: Counter[str] = Counter()

    for clean_row in rows:
        row = dict(clean_row)
        if rng.random() < dirty_rate:
            n_issues = rng.randint(1, MAX_ISSUES_PER_ROW)
            counts.update(_apply_random_issues(row, schema, rng, day, issues, n_issues))
        result.append(row)

        if schema.business_key and rng.random() < dirty_rate * DUPLICATE_SHARE:
            result.append(_duplicate(row, schema, rng))
            counts["duplicate_business_key"] += 1

    return result, counts
