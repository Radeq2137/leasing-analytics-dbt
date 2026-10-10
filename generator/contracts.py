"""Generation of the raw ``contracts`` table (see docs/02-data-contract.md, section 2)."""

import random
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from typing import NamedTuple

from faker import Faker

from generator.dirty import IssueFn, inject_dirty_data, parse_decimal
from generator.schema import Row, TableSchema

FAKER_LOCALE = "pl_PL"
CENT = Decimal("0.01")
VAT_RATE = Decimal("0.23")

N_CUSTOMERS = 500
N_VENDORS = 50
STATUS_ON_SIGNING = "active"
INCLUDE_IN_STATS_YES_SHARE = 0.85
# Share of optional fields that are legitimately left blank in clean data.
OPTIONAL_BLANK_SHARE = 0.05
# Factor used to inject a net value above the asset price.
NET_ABOVE_PRICE_FACTOR = Decimal("1.10")


class AssetType(NamedTuple):
    """Weight and gross price range (PLN) of a leased asset type."""

    weight: int
    min_price: int
    max_price: int


ASSET_TYPES: dict[str, AssetType] = {
    "car": AssetType(50, 60_000, 250_000),
    "truck": AssetType(10, 200_000, 600_000),
    "machinery": AssetType(20, 100_000, 1_500_000),
    "it_equipment": AssetType(15, 10_000, 150_000),
    "medical_equipment": AssetType(5, 50_000, 800_000),
}
CUSTOMER_TYPE_WEIGHTS: dict[str, int] = {"company": 60, "sole_trader": 30, "individual": 10}
VENDOR_TYPES = ("dealer", "manufacturer", "broker")
TERM_MONTHS = (12, 24, 36, 48, 60, 72, 84)
DOWN_PAYMENT_PCT = (0, 5, 10, 15, 20, 30)
EMAIL_DOMAINS = ("example.com", "example.pl")
VOIVODESHIPS = (
    "dolnośląskie", "kujawsko-pomorskie", "lubelskie", "lubuskie",
    "łódzkie", "małopolskie", "mazowieckie", "opolskie",
    "podkarpackie", "podlaskie", "pomorskie", "śląskie",
    "świętokrzyskie", "warmińsko-mazurskie", "wielkopolskie", "zachodniopomorskie",
)

SCHEMA = TableSchema(
    name="contracts",
    columns=(
        "transaction_id", "contract_id", "customer_id", "customer_type", "customer_email",
        "vendor_id", "vendor_type", "asset_type", "asset_price", "net_value",
        "down_payment_pct", "term_months", "signed_date",
        "delivery_street", "delivery_city", "delivery_postal_code", "delivery_region",
        "status", "INCLUDE_IN_STATS",
    ),
    mandatory=frozenset({
        "transaction_id", "contract_id", "customer_id", "customer_type", "vendor_id",
        "vendor_type", "asset_type", "asset_price", "net_value", "term_months",
        "signed_date", "status", "INCLUDE_IN_STATS",
    }),
    numeric=frozenset({"asset_price", "net_value", "down_payment_pct", "term_months"}),
    dates=frozenset({"signed_date"}),
    amounts=frozenset({"asset_price", "net_value"}),
    categorical=frozenset({"customer_type", "vendor_type", "asset_type", "status"}),
    emails=frozenset({"customer_email"}),
    flags=frozenset({"INCLUDE_IN_STATS"}),
    business_key="contract_id",
    row_id="transaction_id",
)


@dataclass(frozen=True)
class CustomerProfile:
    """Attributes that stay the same for a customer across all their contracts."""

    customer_id: str
    customer_type: str
    customer_email: str


@dataclass(frozen=True)
class Contract:
    """One clean, typed lease contract, before serialization to raw text."""

    transaction_id: uuid.UUID
    contract_id: str
    customer: CustomerProfile
    vendor_id: str
    vendor_type: str
    asset_type: str
    asset_price: Decimal
    net_value: Decimal
    down_payment_pct: Decimal | None
    term_months: int
    signed_date: date
    delivery_street: str | None
    delivery_city: str | None
    delivery_postal_code: str | None
    delivery_region: str | None
    status: str
    include_in_stats: bool

    def to_raw_row(self) -> Row:
        """Serialize the contract to a raw CSV row.

        Returns:
            Row with every value as text; missing optional values are blank.
        """
        return {
            "transaction_id": str(self.transaction_id),
            "contract_id": self.contract_id,
            "customer_id": self.customer.customer_id,
            "customer_type": self.customer.customer_type,
            "customer_email": self.customer.customer_email,
            "vendor_id": self.vendor_id,
            "vendor_type": self.vendor_type,
            "asset_type": self.asset_type,
            "asset_price": str(self.asset_price),
            "net_value": str(self.net_value),
            "down_payment_pct": "" if self.down_payment_pct is None else str(self.down_payment_pct),
            "term_months": str(self.term_months),
            "signed_date": self.signed_date.isoformat(),
            "delivery_street": self.delivery_street or "",
            "delivery_city": self.delivery_city or "",
            "delivery_postal_code": self.delivery_postal_code or "",
            "delivery_region": self.delivery_region or "",
            "status": self.status,
            "INCLUDE_IN_STATS": "Y" if self.include_in_stats else "N",
        }


@lru_cache(maxsize=N_CUSTOMERS)
def customer_profile(customer_no: int) -> CustomerProfile:
    """Build the stable profile of a customer.

    The profile is seeded by the customer number only, so the same customer
    always has the same type and e-mail, no matter which day is generated.

    Args:
        customer_no: Customer number, 1..N_CUSTOMERS.

    Returns:
        The customer's profile.
    """
    rng = random.Random(customer_no)
    fake = Faker(FAKER_LOCALE)
    fake.seed_instance(customer_no)
    customer_type = rng.choices(list(CUSTOMER_TYPE_WEIGHTS), weights=list(CUSTOMER_TYPE_WEIGHTS.values()))[0]
    return CustomerProfile(
        customer_id=f"CU-{customer_no:05d}",
        customer_type=customer_type,
        customer_email=f"{fake.user_name()}@{rng.choice(EMAIL_DOMAINS)}",
    )


def _money(value: Decimal) -> Decimal:
    """Round an amount to cents (half up, as in accounting)."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _optional(value: str, rng: random.Random) -> str | None:
    """Return ``value``, or None with probability ``OPTIONAL_BLANK_SHARE``."""
    return None if rng.random() < OPTIONAL_BLANK_SHARE else value


def generate_contract(day: date, sequence_no: int, rng: random.Random, fake: Faker) -> Contract:
    """Generate one clean contract signed on ``day``.

    Args:
        day: Business day the contract is signed on.
        sequence_no: Number of the contract within the day, starting at 1.
        rng: Seeded random generator.
        fake: Seeded Faker instance, used for delivery addresses.

    Returns:
        A clean, typed contract.
    """
    asset_type = rng.choices(list(ASSET_TYPES), weights=[a.weight for a in ASSET_TYPES.values()])[0]
    asset = ASSET_TYPES[asset_type]
    asset_price = _money(Decimal(rng.randint(asset.min_price * 100, asset.max_price * 100)) / 100)

    down_payment_pct = Decimal(rng.choice(DOWN_PAYMENT_PCT))
    net_value = _money(asset_price / (1 + VAT_RATE) * (1 - down_payment_pct / 100))

    vendor_no = rng.randint(1, N_VENDORS)
    return Contract(
        transaction_id=uuid.UUID(int=rng.getrandbits(128), version=4),
        contract_id=f"CT-{day:%Y%m%d}-{sequence_no:04d}",
        customer=customer_profile(rng.randint(1, N_CUSTOMERS)),
        vendor_id=f"VN-{vendor_no:04d}",
        # Derived from the vendor number, so a vendor always has the same type.
        vendor_type=VENDOR_TYPES[vendor_no % len(VENDOR_TYPES)],
        asset_type=asset_type,
        asset_price=asset_price,
        net_value=net_value,
        down_payment_pct=None if rng.random() < OPTIONAL_BLANK_SHARE else down_payment_pct,
        term_months=rng.choice(TERM_MONTHS),
        signed_date=day,
        delivery_street=_optional(fake.street_address(), rng),
        delivery_city=_optional(fake.city(), rng),
        delivery_postal_code=_optional(fake.postcode(), rng),
        delivery_region=_optional(rng.choice(VOIVODESHIPS), rng),
        status=STATUS_ON_SIGNING,
        include_in_stats=rng.random() < INCLUDE_IN_STATS_YES_SHARE,
    )


def net_value_above_price(row: Row, schema: TableSchema, rng: random.Random, day: date) -> bool:
    """Set ``net_value`` above ``asset_price`` (contracts-specific issue, warning)."""
    price = parse_decimal(row.get("asset_price", ""))
    if price is None or price <= 0:
        return False
    row["net_value"] = str(_money(price * NET_ABOVE_PRICE_FACTOR))
    return True


CONTRACT_ISSUES: dict[str, IssueFn] = {"net_value_above_price": net_value_above_price}


def build_raw_rows(day: date, n_rows: int, dirty_rate: float, seed: int) -> tuple[list[Row], Counter[str]]:
    """Generate the raw ``contracts`` rows for one business day.

    Args:
        day: Business day to generate.
        n_rows: Number of contracts signed that day. Must be >= 0.
        dirty_rate: Probability (0-1) that a row gets a data-quality issue.
        seed: Base random seed; combined with the table and day, so every
            day is reproducible on its own.

    Returns:
        Raw rows (all values as text) and a count of injected issues by name.

    Raises:
        ValueError: If ``n_rows`` is negative or ``dirty_rate`` is outside 0-1.
    """
    if n_rows < 0:
        raise ValueError(f"n_rows must be >= 0, got {n_rows}")

    rng = random.Random(f"{seed}-{SCHEMA.name}-{day.isoformat()}")
    fake = Faker(FAKER_LOCALE)
    fake.seed_instance(rng.getrandbits(32))

    clean_rows = [generate_contract(day, i, rng, fake).to_raw_row() for i in range(1, n_rows + 1)]
    return inject_dirty_data(clean_rows, SCHEMA, day, dirty_rate, rng, extra_issues=CONTRACT_ISSUES)
