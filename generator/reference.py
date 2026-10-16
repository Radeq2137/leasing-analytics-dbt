"""Reference data shared by the generator and dbt (the seed files in ``dbt/seeds/``).

The generator and dbt read the SAME file, so the cities the generator draws are exactly the cities dbt
validates against (docs/02-data-contract.md, "Reference data").
"""

import csv
import random
from functools import lru_cache
from pathlib import Path

CITY_REGION_SEED = Path(__file__).resolve().parent.parent / "dbt" / "seeds" / "ref_city_region.csv"


def group_cities_by_region(rows: list[dict[str, str]]) -> dict[str, list[str]]:
    """Group city names under their region.

    Args:
        rows: Rows like ``{"city": "Lublin", "region": "lubelskie"}``, e.g. from ``csv.DictReader``.

    Returns:
        ``{region: [cities]}``; regions in order of first appearance, cities in the order of the rows.

    Examples:
        >>> group_cities_by_region([{"city": "Lublin", "region": "lubelskie"}])
        {'lubelskie': ['Lublin']}
    """
    cities_by_region: dict[str, list[str]] = {}
    for row in rows:
        cities_by_region.setdefault(row["region"], []).append(row["city"])
    return cities_by_region


def load_city_region(path: Path = CITY_REGION_SEED) -> dict[str, list[str]]:
    """Read the city/region seed file.

    Args:
        path: CSV file with the columns ``city`` and ``region``.

    Returns:
        ``{region: [cities]}`` (see ``group_cities_by_region``).

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    with path.open(newline="", encoding="utf-8") as f:
        return group_cities_by_region(list(csv.DictReader(f)))


@lru_cache(maxsize=None)
def cities_by_region() -> dict[str, list[str]]:
    """Return the city/region seed, read from disk only once (callers must not modify it)."""
    return load_city_region()


def pick_region_and_city(rng: random.Random) -> tuple[str, str]:
    """Draw a region and then a city that BELONGS to that region.

    Args:
        rng: Seeded random generator.

    Returns:
        ``(region, city)`` - always a consistent pair from the seed.
    """
    regions = cities_by_region()
    region = rng.choice(sorted(regions))
    return region, rng.choice(regions[region])
