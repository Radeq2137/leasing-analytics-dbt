"""Column-level metadata of raw tables.

A ``TableSchema`` is the code version of a table section in
docs/02-data-contract.md. The dirty-data injector uses it to know which
columns are mandatory, numeric, dates, etc., so it stays table-agnostic.
"""

from dataclasses import dataclass

Row = dict[str, str]
"""One raw CSV row: column name -> value as text (the raw layer is all text)."""


@dataclass(frozen=True)
class TableSchema:
    """Column-level metadata of one raw table.

    Attributes:
        name: Table name; also used as the S3 prefix and the file name.
        columns: All columns, in file order.
        mandatory: Columns that must not be blank.
        numeric: Columns that must parse as numbers.
        dates: Columns that must parse as ISO dates (``YYYY-MM-DD``).
        amounts: Numeric columns that must be greater than zero.
        categorical: Text columns with a fixed set of allowed values.
        emails: Columns holding e-mail addresses.
        flags: ``Y``/``N`` flag columns.
        business_key: Column that must be unique, if any.
        row_id: Technical id that is unique per row, if any.
    """

    name: str
    columns: tuple[str, ...]
    mandatory: frozenset[str]
    numeric: frozenset[str] = frozenset()
    dates: frozenset[str] = frozenset()
    amounts: frozenset[str] = frozenset()
    categorical: frozenset[str] = frozenset()
    emails: frozenset[str] = frozenset()
    flags: frozenset[str] = frozenset()
    business_key: str | None = None
    row_id: str | None = None
