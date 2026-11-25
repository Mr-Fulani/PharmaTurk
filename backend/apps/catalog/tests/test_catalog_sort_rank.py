"""Порядок списков медикаментов и БАДов: ранг «Популярные» и устойчивые сортировки."""

import uuid

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.catalog.models import (
    Category,
    Favorite,
    MedicineProduct,
    ProductMarketCheck,
    SupplementProduct,
)
from apps.catalog.models_search import SearchDemand
from apps.catalog.services.catalog_sort_rank import (
    DEMAND_LEVELS,
    compute_sort_rank,
    demand_for_name,
    demand_levels,
    recompute_sort_ranks,
)

URL = "/api/catalog/medicines/products"
SUPPLEMENTS_URL = "/api/catalog/supplements/products"


def _rank(**overrides):
    params = dict(
        has_price=True, is_available=True, is_featured=False,
        interest=0, has_image=False, has_ru_description=False,
    )
    params.update(overrides)
    return compute_sort_rank(**params)


def test_rank_puts_price_before_demand_and_demand_before_card_quality():
    assert _rank() > _rank(is_available=False) > _rank(has_price=False)
    assert _rank(has_price=False, is_featured=True, interest=9_999) < _rank()
    assert _rank(is_featured=True) > _rank(interest=10_000, has_image=True)
    assert _rank(interest=1) > _rank(has_image=True, has_ru_description=True)


@pytest.fixture
def medicines(db):
    suffix = uuid.uuid4().hex[:8]
    category = Category.objects.create(name="Медикаменты", slug=f"medicines-{suffix}")

    def make(name, **fields):
        return MedicineProduct.objects.create(
            name=name, slug=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}",
            category=category, currency="TRY", is_active=True, **fields,
        )

    return category, make


def _names(category, ordering, url=URL):
    response = APIClient().get(
        url, {"category_slug": category.slug, "ordering": ordering, "view": "card"}
    )
    assert response.status_code == 200
    return [item["name"] for item in response.data["results"]]


def test_popular_order_follows_recomputed_rank(medicines):
    category, make = medicines
    make("Unpriced", price=None)
    plain = make("Plain", price=10)
    wanted = make("Wanted", price=10)
    favorite = make("Favorite", price=10)
    wanted.refresh_from_db()  # shadow-Product создаётся в save()
    ProductMarketCheck.objects.create(
        product=wanted.base_product, source="ilacfiyati",
        source_url="https://example.com/wanted", request_count=5,
    )
    Favorite.objects.create(
        session_key="rank-test",
        content_type=ContentType.objects.get_for_model(MedicineProduct),
        object_id=favorite.pk,
    )
    plain.refresh_from_db()  # save() пишет shadow-sync повторно
    updated_at = plain.updated_at

    assert recompute_sort_ranks(MedicineProduct) == 4
    assert _names(category, "popular") == ["Wanted", "Favorite", "Plain", "Unpriced"]

    plain.refresh_from_db()
    assert plain.updated_at == updated_at
    assert recompute_sort_ranks(MedicineProduct) == 0


def test_price_desc_keeps_unpriced_last_and_ties_are_stable(medicines):
    category, make = medicines
    make("Unpriced", price=None)
    first = make("Same", price=5)
    second = make("Same", price=5)
    make("Expensive", price=50)

    assert _names(category, "price_desc") == ["Expensive", "Same", "Same", "Unpriced"]
    assert _names(category, "price_asc")[-1] == "Unpriced"

    response = APIClient().get(
        URL, {"category_slug": category.slug, "ordering": "name_asc", "view": "card"}
    )
    same_ids = [item["id"] for item in response.data["results"] if item["name"] == "Same"]
    assert same_ids == [first.pk, second.pk]


def test_supplements_popular_order_follows_recomputed_rank(db):
    category = Category.objects.create(name="БАДы", slug=f"supplements-{uuid.uuid4().hex[:8]}")

    def make(name, price):
        return SupplementProduct.objects.create(
            name=name, slug=f"{name.lower()}-{uuid.uuid4().hex[:6]}",
            category=category, currency="TRY", is_active=True, price=price,
        )

    make("Unpriced", None)
    make("Plain", 10)
    wanted = make("Wanted", 10)
    Favorite.objects.create(
        session_key="rank-test",
        content_type=ContentType.objects.get_for_model(SupplementProduct),
        object_id=wanted.pk,
    )

    assert recompute_sort_ranks(SupplementProduct) == 3
    assert _names(category, "popular", SUPPLEMENTS_URL) == ["Wanted", "Plain", "Unpriced"]


# ─── Спрос из поиска (docs/CATALOG_SEARCH_DEMAND.md) ───


def test_search_demand_outranks_everything_and_fits_the_column():
    best_without_demand = _rank(is_featured=True, interest=10_000, has_image=True, has_ru_description=True)
    assert _rank(has_price=False, is_available=False, demand=1) > best_without_demand
    assert _rank(demand=2, has_price=False) > _rank(demand=1)
    assert _rank(demand=1) > _rank(demand=1, is_available=False)
    assert _rank(demand=DEMAND_LEVELS + 5, is_featured=True, interest=10_000, has_image=True) <= 2_147_483_647


def test_demand_matches_start_of_name_by_whole_words(db):
    for prefix, frequency in (("TYLOLHOT", 40_000), ("A-FERIN", 6_000), ("PAROL", 700), ("CLEOCIN T", 300)):
        SearchDemand.objects.create(name_prefix=prefix, frequency=frequency)
    SearchDemand.objects.create(product_type="supplements", name_prefix="SOLGAR", frequency=5)
    levels = demand_levels("medicines")

    assert demand_for_name("TYLOL HOT D 500 мг, 12 саше", levels) == 4
    assert demand_for_name("Tylolhot Day 20 г", levels) == 4
    assert demand_for_name("A-FERIN (парацетамол) 30 капсул", levels) == 3
    assert demand_for_name("PAROL-K 500 мг", levels) == 2
    assert demand_for_name("CLEOCIN T 1%, раствор", levels) == 1
    assert demand_for_name("CLEOCIN 150 мг", levels) == 0
    assert demand_for_name("PAROLEX 20 мг", levels) == 0
    assert demand_for_name("SOLGAR Омниум", levels) == 0
    assert demand_for_name("", levels) == 0


def test_popular_list_puts_searched_names_first_without_extra_queries(medicines):
    category, make = medicines
    make("PLAIN 10 мг", price=10)
    make("MAJEZIK 100 мг", price=10)
    make("OZEMPIC 1 мг", price=None, is_available=False)
    params = {"category_slug": category.slug, "ordering": "popular", "view": "card"}

    recompute_sort_ranks(MedicineProduct)
    with CaptureQueriesContext(connection) as before:
        APIClient().get(URL, params)

    SearchDemand.objects.create(name_prefix="OZEMPIC", frequency=310_620)
    SearchDemand.objects.create(name_prefix="MAJEZIK", frequency=17_773)
    recompute_sort_ranks(MedicineProduct)
    with CaptureQueriesContext(connection) as after:
        assert _names(category, "popular") == ["OZEMPIC 1 мг", "MAJEZIK 100 мг", "PLAIN 10 мг"]

    assert len(after) == len(before)
    assert not any("searchdemand" in query["sql"] for query in after)


def test_demand_commands_show_first_and_write_only_with_apply(medicines, tmp_path, capsys):
    category, make = medicines
    make("PLAIN 10 мг", price=10)
    wanted = make("MAJEZIK 100 мг", price=10)
    recompute_sort_ranks(MedicineProduct)
    wanted.refresh_from_db()
    rank = wanted.sort_rank
    path = tmp_path / "demand.csv"
    path.write_text("name,frequency,note\nMAJEZIK,17773,majezik\n", encoding="utf-8")

    call_command("import_search_demand", str(path))
    assert not SearchDemand.objects.exists()
    call_command("import_search_demand", str(path), "--apply")
    call_command("import_search_demand", str(path), "--apply")
    assert list(SearchDemand.objects.values_list("product_type", "name_prefix", "frequency")) == [
        ("medicines", "MAJEZIK", 17773)
    ]

    capsys.readouterr()
    call_command("recompute_sort_ranks", "--top", "1")
    output = capsys.readouterr().out
    assert "место сменят 1 из 2" in output and "MAJEZIK 100 мг" in output
    wanted.refresh_from_db()
    assert wanted.sort_rank == rank

    call_command("recompute_sort_ranks", "--apply")
    wanted.refresh_from_db()
    assert wanted.sort_rank > rank
    assert _names(category, "popular")[0] == "MAJEZIK 100 мг"
