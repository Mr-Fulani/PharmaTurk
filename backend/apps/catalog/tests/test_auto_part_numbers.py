"""Автозапчасти: нормализованный артикул, номера (OEM, аналоги) и применимость."""

import pytest
from django.db import IntegrityError, transaction

from apps.catalog.models import AutoPartFitment, AutoPartNumber, AutoPartProduct
from apps.catalog.utils.part_numbers import normalize_part_number, vehicle_slug


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1K0 615 301 AA", "1K0615301AA"),
        ("1k0-615-301aa", "1K0615301AA"),
        ("0 986 494.104", "0986494104"),
        ("FDB/1641", "FDB1641"),
        ("LEMFÖRDER 33626 01", "LEMFORDER3362601"),
        ("İÇ-12ş", "IC12S"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_part_number(raw, expected):
    assert normalize_part_number(raw) == expected


def test_vehicle_slug():
    assert vehicle_slug("MERCEDES-BENZ") == "mercedes-benz"
    assert vehicle_slug("CITROËN") == vehicle_slug("CITROЁN") == "citroen"
    assert vehicle_slug("X-TRAIL") == "x-trail"


@pytest.mark.django_db
def test_part_number_is_normalized_on_save():
    part = AutoPartProduct.objects.create(name="Колодки", slug="pads-1", part_number="0 986 494-104")
    assert part.part_number_normalized == "0986494104"

    part.part_number = "fdb 1641"
    part.save(update_fields=["part_number"])
    part.refresh_from_db()
    assert part.part_number_normalized == "FDB1641"
    assert list(AutoPartProduct.objects.filter(part_number_normalized=normalize_part_number("FDB-1641"))) == [part]


@pytest.mark.django_db
def test_number_is_unique_per_product_and_kind_whatever_the_spelling():
    part = AutoPartProduct.objects.create(name="Колодки", slug="pads-2")
    other = AutoPartProduct.objects.create(name="Диск", slug="disc-2")
    number = AutoPartNumber.objects.create(product=part, number="1K0 615 301 AA", maker="VW")
    assert (number.number_normalized, number.kind) == ("1K0615301AA", "oem")

    with pytest.raises(IntegrityError), transaction.atomic():
        AutoPartNumber.objects.create(product=part, number="1k0-615-301aa")
    # тот же номер как аналог и у другой детали — можно
    AutoPartNumber.objects.create(product=part, number="1K0615301AA", kind="cross")
    AutoPartNumber.objects.create(product=other, number="1K0615301AA")
    assert AutoPartNumber.objects.filter(number_normalized="1K0615301AA").count() == 3


@pytest.mark.django_db
def test_fitment_slugs_and_cascade():
    part = AutoPartProduct.objects.create(name="Колодки", slug="pads-3")
    fitment = AutoPartFitment.objects.create(
        product=part, make="MERCEDES-BENZ", model="C-CLASS", generation="C-Class (W203) (05.2000 - 08.2007)",
        year_from=2000, month_from=5, year_to=2007, month_to=8, engine="C 180", power_kw=95, power_hp=129,
    )
    assert (fitment.make_slug, fitment.model_slug) == ("mercedes-benz", "c-class")
    assert list(AutoPartFitment.objects.filter(make_slug="mercedes-benz", model_slug="c-class")) == [fitment]

    part.delete()
    assert not AutoPartFitment.objects.exists() and not AutoPartNumber.objects.exists()


@pytest.fixture
def admin_client(client, django_user_model, settings):
    # страницы админки ссылаются на статику; в тестах манифеста collectstatic нет
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    client.force_login(
        django_user_model.objects.create_superuser("parts-admin", "parts-admin@example.com", "x" * 20)
    )
    return client


@pytest.mark.django_db
def test_admin_shows_numbers_and_fitments_in_russian(admin_client):
    from django.urls import reverse

    part = AutoPartProduct.objects.create(name="Колодки", slug="pads-4", part_number="FDB 1641")
    AutoPartNumber.objects.create(product=part, number="1K0 698 151", maker="VW", source="aloparca")
    AutoPartFitment.objects.create(product=part, make="VOLKSWAGEN", model="GOLF", engine="1.6", source="aloparca")

    card = admin_client.get(reverse("admin:catalog_autopartproduct_change", args=[part.pk])).content.decode()
    assert "Номера: OEM и аналоги" in card and "1K0 698 151" in card
    assert "Автомобилей: 1" in card and f"product__id__exact={part.pk}" in card

    # поиск по номеру без пробелов находит номер, записанный с пробелами
    numbers = admin_client.get(reverse("admin:catalog_autopartnumber_changelist"), {"q": "1k0-698151"})
    assert "1K0 698 151" in numbers.content.decode()
    fitments = admin_client.get(reverse("admin:catalog_autopartfitment_changelist"), {"product__id__exact": part.pk})
    assert "VOLKSWAGEN" in fitments.content.decode()
    products = admin_client.get(reverse("admin:catalog_autopartproduct_changelist"), {"q": "1K0698151"})
    assert "Колодки" in products.content.decode()
