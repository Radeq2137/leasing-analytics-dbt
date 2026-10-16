"""Customers: the registration timeline and the stable profile of every customer.

See docs/02-data-contract.md, section 3 (``customers``) and section 4 (cross-table rules).
"""

import math
import random
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

from faker import Faker

from generator.dirty import IssueFn, inject_dirty_data
from generator.reference import cities_by_region, pick_region_and_city
from generator.schema import Row, TableSchema

GO_LIVE_DATE = date(2026, 7, 19)  # first day of data: the initial batch registers here
INITIAL_CUSTOMERS = 150  # customers registered on the go-live day
NEW_CUSTOMERS_PER_DAY = 3  # customers registered on every following day

FAKER_LOCALE = "pl_PL"
CUSTOMER_TYPE_WEIGHTS: dict[str, int] = {"company": 60, "sole_trader": 30, "individual": 10}  # share in %
COMPANY_TYPE = "company"
INDIVIDUAL_TYPE = "individual"  # has no industry: it gets PRIVATE_INDUSTRY
INDUSTRIES = ("transport", "construction", "manufacturing", "retail", "healthcare", "it_services", "agriculture")
PRIVATE_INDUSTRY = "private"  # the "industry" of an individual
EMAIL_DOMAINS = ("example.com", "example.pl")  # reserved example domains, no real addresses

COLUMNS = (
    "customer_id", "customer_type", "customer_name", "industry",
    "region", "city", "customer_email", "registration_date",
)

SCHEMA = TableSchema(
    name="customers",
    columns=COLUMNS,
    mandatory=frozenset({"customer_id", "customer_type", "customer_name", "industry", "region", "registration_date"}),
    dates=frozenset({"registration_date"}),
    categorical=frozenset({"customer_type", "industry"}),
    emails=frozenset({"customer_email"}),
    business_key="customer_id",
)


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


def registration_date_of(customer_no) -> date:
    """Return the day the customer with this number registers.

    The inverse of ``customer_numbers_for_day``: the initial batch registers on the go-live day,
    then ``NEW_CUSTOMERS_PER_DAY`` customers register every following day.

    Args:
        customer_no: Customer number, 1, 2, 3, ...

    Returns:
        The registration day.

    Raises:
        ValueError: If ``customer_no`` is smaller than 1; the message contains the number.

    Examples:
        >>> registration_date_of(151)
        datetime.date(2026, 7, 20)
    """

    if customer_no <= 0:
        raise ValueError(f"Expected positive integer number. Got {customer_no}")
    elif customer_no <= INITIAL_CUSTOMERS:
        return GO_LIVE_DATE
    else:
        days_since_start = math.ceil(customer_no / 3) - 50  # - 50 due to 150 initial customers
        return GO_LIVE_DATE + timedelta(days=days_since_start)


@dataclass(frozen=True)
class CustomerProfile:
    """Everything that stays the same for a customer, whatever day is generated."""

    customer_id: str
    customer_type: str
    customer_name: str
    industry: str
    region: str
    city: str
    customer_email: str
    registration_date: date

    def to_raw_row(self) -> Row:
        """Serialize the profile to a raw CSV row (every value as text).

        Returns:
            Row with exactly the columns of ``COLUMNS``.
        """
        return {
            "customer_id": self.customer_id,
            "customer_type": self.customer_type,
            "customer_name": self.customer_name,
            "industry": self.industry,
            "region": self.region,
            "city": self.city,
            "customer_email": self.customer_email,
            "registration_date": self.registration_date.isoformat(),
        }


@lru_cache(maxsize=None)
def _faker() -> Faker:
    """Create one Faker instance (building it is slow); it is re-seeded for every customer."""
    return Faker(FAKER_LOCALE)


@lru_cache(maxsize=None)
def customer_profile(customer_no: int) -> CustomerProfile:
    """Build the stable profile of a customer.

    Everything is seeded by the customer number only, so the same customer always has the same
    type, name, address and e-mail, whichever day or table asks for it. The city always belongs
    to the region (both come from the ``ref_city_region`` seed) and the e-mail is unique per customer.

    Args:
        customer_no: Customer number, 1, 2, 3, ...

    Returns:
        The customer's profile.

    Raises:
        ValueError: If ``customer_no`` is smaller than 1; the message contains the number.
    """
    if customer_no < 1:
        raise ValueError(f"customer_no must be >= 1, got {customer_no}")

    rng = random.Random(f"customer-{customer_no}")
    fake = _faker()
    fake.seed_instance(customer_no)

    customer_type = rng.choices(list(CUSTOMER_TYPE_WEIGHTS), weights=list(CUSTOMER_TYPE_WEIGHTS.values()))[0]
    is_individual = customer_type == INDIVIDUAL_TYPE

    region, city = pick_region_and_city(rng)

    return CustomerProfile(
        customer_id=f"CU-{customer_no:05d}",
        customer_type=customer_type,
        # A company has a company name; a sole trader and an individual are people.
        customer_name=fake.company() if customer_type == COMPANY_TYPE else fake.name(),
        industry=PRIVATE_INDUSTRY if is_individual else rng.choice(INDUSTRIES),
        region=region,
        city=city,
        # The number in the address keeps clean e-mails unique (duplicates are injected on purpose).
        customer_email=f"{fake.user_name()}.{customer_no}@{rng.choice(EMAIL_DOMAINS)}",
        registration_date=registration_date_of(customer_no),
    )


def duplicate_email(row: Row, schema: TableSchema, rng: random.Random, day: date) -> bool:
    """Give the customer the e-mail of an already registered customer (flagged later in dbt)."""
    already_registered = registered_count(day - timedelta(days=1))
    if already_registered < 1:
        return False
    row["customer_email"] = customer_profile(rng.randint(1, already_registered)).customer_email
    return True


def city_region_mismatch(row: Row, schema: TableSchema, rng: random.Random, day: date) -> bool:
    """Replace the city with one from a DIFFERENT region (flagged later in dbt)."""
    regions = cities_by_region()
    region = row.get("region", "")
    if region not in regions:
        return False  # a blank or unknown region never counts as a mismatch
    other_region = rng.choice([r for r in sorted(regions) if r != region])
    row["city"] = rng.choice(regions[other_region])
    return True


CUSTOMER_ISSUES: dict[str, IssueFn] = {
    "duplicate_email": duplicate_email,
    "city_region_mismatch": city_region_mismatch,
}


def build_raw_rows(day: date, n_rows: int, dirty_rate: float, seed: int) -> tuple[list[Row], Counter[str]]:
    """Generate the raw ``customers`` rows for one business day.

    The customers of a day are the ones that register that day (see ``customer_numbers_for_day``).

    Args:
        day: Business day to generate.
        n_rows: Ignored. How many customers register on a day is decided by the timeline
            (``INITIAL_CUSTOMERS`` on go-live, then ``NEW_CUSTOMERS_PER_DAY``); the argument only
            exists so that every table has the same builder signature.
        dirty_rate: Probability (0-1) that a row gets a data-quality issue.
        seed: Base random seed; combined with the table and day, so every day is reproducible.

    Returns:
        Raw rows (all values as text) and a count of injected issues by name.

    Raises:
        ValueError: If ``dirty_rate`` is outside 0-1.
    """
    rng = random.Random(f"{seed}-{SCHEMA.name}-{day.isoformat()}")
    clean_rows = [customer_profile(n).to_raw_row() for n in customer_numbers_for_day(day)]
    return inject_dirty_data(clean_rows, SCHEMA, day, dirty_rate, rng, extra_issues=CUSTOMER_ISSUES)
