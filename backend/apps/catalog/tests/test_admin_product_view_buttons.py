"""Кнопки «Посмотреть на сайте» и «Источник» вверху карточки товара в админке."""
from uuid import uuid4

import pytest
from django.urls import reverse

from apps.catalog.admin_links import SOURCE_BUTTONS_LIMIT, product_view_buttons
from apps.catalog.models import MedicineProduct, Product, ProductSourceOffer


@pytest.fixture(autouse=True)
def site(settings):
    settings.FRONTEND_SITE_URL = "https://site.test"


def _product(**kwargs):
    kwargs.setdefault("slug", f"tovar-{uuid4().hex}")
    kwargs.setdefault("product_type", "accessories")
    return Product.objects.create(name="Товар", **kwargs)


def _offer(product, url, key):
    return ProductSourceOffer.objects.create(
        product=product, parser_key="flo", canonical_url=url, variant_key=key, size_key=key
    )


def _labels(obj):
    return [button["label"] for button in product_view_buttons(obj)]


@pytest.mark.django_db
def test_one_source():
    product = _product(external_url="https://www.lcwaikiki.com/tr-TR/TR/urun/1")
    _offer(product, "https://www.lcwaikiki.com/tr-TR/TR/urun/1", "a")

    buttons = product_view_buttons(product)

    assert [(b["label"], b["url"]) for b in buttons] == [
        ("Посмотреть на сайте", f"https://site.test/product/{product.slug}"),
        ("Источник: lcwaikiki.com", "https://www.lcwaikiki.com/tr-TR/TR/urun/1"),
    ]


@pytest.mark.django_db
def test_type_in_path():
    product = _product(product_type="shoes", slug=f"krossovki-{uuid4().hex}")

    assert product_view_buttons(product)[0]["url"] == f"https://site.test/product/shoes/{product.slug}"


@pytest.mark.django_db
def test_several_sources_without_duplicates(django_assert_max_num_queries):
    product = _product(external_url="https://www.flo.com.tr/urun/a")
    _offer(product, "https://www.flo.com.tr/urun/a", "a1")
    _offer(product, "https://www.flo.com.tr/urun/a", "a2")
    _offer(product, "https://www.flo.com.tr/urun/b", "b")
    _offer(product, "https://www.superstep.com.tr/urun/c", "c")

    with django_assert_max_num_queries(1):
        labels = _labels(product)

    assert labels == [
        "Посмотреть на сайте",
        "Источник: flo.com.tr",
        "Источник: flo.com.tr · 2",
        "Источник: superstep.com.tr",
    ]


@pytest.mark.django_db
def test_more_sources_than_limit():
    product = _product()
    for i in range(SOURCE_BUTTONS_LIMIT + 2):
        _offer(product, f"https://www.flo.com.tr/urun/{i}", str(i))

    buttons = product_view_buttons(product)

    assert len(buttons) == 1 + SOURCE_BUTTONS_LIMIT + 1
    assert buttons[-1]["label"] == "Ещё источников: 2"
    assert buttons[-1]["url"] == (
        reverse("admin:catalog_productsourceoffer_changelist") + f"?product__id__exact={product.pk}"
    )


@pytest.mark.django_db
def test_no_source():
    product = _product(external_url="ftp://example.com/x")

    assert _labels(product) == ["Посмотреть на сайте"]


@pytest.mark.django_db
def test_hidden_product_has_no_site_button():
    hidden = _product(is_active=False, external_url="https://www.flo.com.tr/urun/a")
    shadow = _product(external_data={"source_variant_slug": "x"})

    assert _labels(hidden) == ["Источник: flo.com.tr"]
    assert _labels(shadow) == []


@pytest.mark.django_db
def test_medicine_record_uses_base_product_sources():
    slug = f"lekarstvo-{uuid4().hex}"
    medicine = MedicineProduct.objects.create(
        name="Лекарство", slug=slug, external_url="https://ilacfiyati.com/ilaclar/x"
    )
    medicine.refresh_from_db()
    _offer(medicine.base_product, "https://www.ilacrehberi.com/v/x", "x")

    buttons = product_view_buttons(medicine)

    assert [(b["label"], b["url"]) for b in buttons] == [
        ("Посмотреть на сайте", f"https://site.test/product/{slug}"),
        ("Источник: ilacfiyati.com", "https://ilacfiyati.com/ilaclar/x"),
        ("Источник: ilacrehberi.com", "https://www.ilacrehberi.com/v/x"),
    ]


@pytest.mark.django_db
def test_buttons_on_admin_pages(client, django_user_model):
    client.force_login(django_user_model.objects.create_superuser("links-admin", "links@example.com", "x" * 20))
    slug = f"lekarstvo-{uuid4().hex}"
    medicine = MedicineProduct.objects.create(
        name="Лекарство", slug=slug, external_url='https://ilacfiyati.com/ilaclar/x?a="><b>'
    )
    medicine.refresh_from_db()

    for url in (
        reverse("admin:catalog_medicineproduct_change", args=[medicine.pk]),
        reverse("admin:catalog_product_change", args=[medicine.base_product_id]),
    ):
        html = client.get(url).content.decode()
        assert (
            f'<a href="https://site.test/product/{slug}" class="viewsitelink" target="_blank" '
            'rel="noopener noreferrer"'
        ) in html
        assert "Источник: ilacfiyati.com" in html
        assert 'href="https://ilacfiyati.com/ilaclar/x?a=&quot;&gt;&lt;b&gt;"' in html

    # У не-товара кнопок нет, страница открывается
    offers = client.get(reverse("admin:catalog_productsourceoffer_changelist"))
    assert offers.status_code == 200
