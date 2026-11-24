"""Карточка автозапчасти в API: OEM-номера, сводка применимости и строки марки по запросу."""

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import AutoPartFitment, AutoPartNumber, AutoPartProduct, Category

URL = "/api/catalog/auto-parts/products/{slug}"


@pytest.fixture
def part(db):
    root = Category.objects.create(name="Автозапчасти", slug="auto-parts")
    part = AutoPartProduct.objects.create(
        name="Тормозной диск Blue Print ADB114382", slug="brake-disc-adb114382", category=root,
        part_number="ADB114382", price=5980, currency="TRY",
    )
    AutoPartNumber.objects.create(product=part, number="34 21 6 792 227", maker="BMW", source="aloparca")
    AutoPartNumber.objects.create(product=part, number="DF6513S", kind="cross", maker="TRW")
    rows = [
        ("BMW", "3 Serisi", "3 Sedan (F30, F80) (03.2011 - 10.2018)", "320 d", 135, 184, 2012, 3, 2018, 10),
        ("BMW", "3 Serisi", "3 Touring (F31) (07.2012 - 06.2019)", "318 d", 105, 143, 2012, 7, None, None),
        ("BMW", "4 Serisi", "4 Coupe (F32, F82) (07.2013 - ...)", "420 i", 135, 184, 2013, 7, None, None),
        ("MERCEDES-BENZ", "C-CLASS", "C-Class (W205) (12.2013 - ...)", "C 180", 115, 156, 2014, 1, None, None),
    ]
    for make, model, generation, engine, kw, hp, year_from, month_from, year_to, month_to in rows:
        AutoPartFitment.objects.create(
            product=part, make=make, model=model, generation=generation, engine=engine, power_kw=kw, power_hp=hp,
            year_from=year_from, month_from=month_from, year_to=year_to, month_to=month_to, source="aloparca",
        )
    return part


def test_card_has_numbers_and_fitment_summary_without_rows(part):
    data = APIClient().get(URL.format(slug=part.slug), HTTP_ACCEPT_LANGUAGE="ru").json()

    assert data["part_number"] == "ADB114382"
    assert data["oem_numbers"] == [
        {"number": "DF6513S", "kind": "cross", "maker": "TRW"},
        {"number": "34 21 6 792 227", "kind": "oem", "maker": "BMW"},
    ]
    assert data["fitment_summary"] == {
        "count": 4,
        "makes": [
            {"slug": "bmw", "name": "BMW", "count": 3, "models": ["3 серии", "4 серии"]},
            {"slug": "mercedes-benz", "name": "Mercedes-Benz", "count": 1, "models": ["C-Class"]},
        ],
    }
    assert "generation" not in str(data["fitment_summary"])


def test_summary_models_follow_the_request_language(part):
    data = APIClient().get(URL.format(slug=part.slug), HTTP_ACCEPT_LANGUAGE="en").json()

    assert data["fitment_summary"]["makes"][0]["models"] == ["3 Series", "4 Series"]


def test_fitments_of_one_make_are_loaded_on_demand(part):
    client = APIClient()

    data = client.get(URL.format(slug=part.slug) + "/fitments", {"make": "bmw", "page_size": 500}).json()

    assert data["count"] == 3
    assert data["results"][0] == {
        "model": "3 Serisi", "generation": "3 Sedan (F30, F80) (03.2011 - 10.2018)", "engine": "320 d",
        "power_kw": 135, "power_hp": 184, "year_from": 2012, "month_from": 3, "year_to": 2018, "month_to": 10,
        "note": "",
    }
    assert client.get(URL.format(slug=part.slug) + "/fitments").status_code == 400
    assert client.get(URL.format(slug=part.slug) + "/fitments", {"make": "audi"}).json()["count"] == 0


def test_card_queries_do_not_grow_with_fitment_rows(part, django_assert_max_num_queries):
    client = APIClient()
    with django_assert_max_num_queries(60) as before:
        client.get(URL.format(slug=part.slug))
    for index in range(40):
        AutoPartFitment.objects.create(product=part, make=f"MAKE{index}", model="X", source="aloparca")
        AutoPartNumber.objects.create(product=part, number=f"N{index:05d}", source="aloparca")
    with django_assert_max_num_queries(len(before.captured_queries)):
        client.get(URL.format(slug=part.slug))


def test_page_resolve_carries_the_same_blocks(part):
    """Страница товара берёт карточку из resolve — блоки номеров и применимости должны быть в нём."""
    data = APIClient().get(f"/api/catalog/products/resolve/{part.slug}", HTTP_ACCEPT_LANGUAGE="ru").json()

    payload = data.get("payload") or data.get("product") or data
    assert payload["fitment_summary"]["count"] == 4
    assert [row["number"] for row in payload["oem_numbers"]] == ["DF6513S", "34 21 6 792 227"]
