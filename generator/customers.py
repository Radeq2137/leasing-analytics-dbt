"""Timeline of customer registrations: who exists on a given day (see docs/02-data-contract.md, section 3)."""

from datetime import date, timedelta

GO_LIVE_DATE = date(2026, 7, 19)  # first day of data: the initial batch registers here
INITIAL_CUSTOMERS = 150  # customers registered on the go-live day
NEW_CUSTOMERS_PER_DAY = 3  # customers registered on every following day

def registered_count(day: date) -> int:
    """Return how many customers are registered on ``day`` or earlier.

    Args:
        day: Business day.

    Returns:
        0 before the go-live day; otherwise the initial batch plus the new customers of every day since.
    """
        
    if day < GO_LIVE_DATE:
        return 0

    return INITIAL_CUSTOMERS + NEW_CUSTOMERS_PER_DAY * (day - GO_LIVE_DATE).days

def customer_numbers_for_day(day: date) -> range:

    """Return the numbers of the customers who register on ``day``.

    Customers are numbered 1, 2, 3, ... in the order they register, so the new customers of a
    day are the numbers between yesterday's total and today's total.

    Args:
        day: Business day.

    Returns:
        The new customer numbers as a ``range``: 1..150 on the go-live day, then 3 per day;
        empty before go-live.

    Examples:
        >>> list(customer_numbers_for_day(date(2026, 7, 20)))
        [151, 152, 153]
    """

    yesterday = day - timedelta(days=1)

    return range(registered_count(yesterday) + 1, registered_count(day) + 1)
