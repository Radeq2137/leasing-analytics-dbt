"""Tests for generator.reference (reads the real seed file, no AWS)."""

from generator.contracts import VOIVODESHIPS
from generator.reference import group_cities_by_region, load_city_region


def test_group_cities_by_region_keeps_order() -> None:
    rows = [
        {"city": "Lublin", "region": "lubelskie"},
        {"city": "Gdańsk", "region": "pomorskie"},
        {"city": "Zamość", "region": "lubelskie"},
    ]
    assert group_cities_by_region(rows) == {"lubelskie": ["Lublin", "Zamość"], "pomorskie": ["Gdańsk"]}


def test_group_cities_by_region_empty() -> None:
    assert group_cities_by_region([]) == {}


def test_seed_has_every_voivodeship_with_three_cities() -> None:
    cities_by_region = load_city_region()
    assert len(cities_by_region) == 16
    assert all(len(cities) == 3 for cities in cities_by_region.values())


def test_seed_regions_match_the_generator_voivodeship_list() -> None:
    """The two lists must stay in sync: the contract validates city/region against this seed."""
    assert set(load_city_region()) == set(VOIVODESHIPS)


def test_seed_assigns_every_city_to_exactly_one_region() -> None:
    all_cities = [city for cities in load_city_region().values() for city in cities]
    assert len(all_cities) == len(set(all_cities)) == 48


def test_seed_polish_characters_survive() -> None:
    cities_by_region = load_city_region()
    assert "Łódź" in cities_by_region["łódzkie"]
    assert "Częstochowa" in cities_by_region["śląskie"]
