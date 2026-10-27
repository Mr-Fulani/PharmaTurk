"""YML-фид: потоковая сборка без N+1, готовые файлы, эндпоинт и админка ВК."""
import io
import xml.etree.ElementTree as ET
from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.catalog.models import (
    Category,
    GlobalAttributeKey,
    GlobalAttributeKeyTranslation,
    Product,
    ProductAttributeValue,
    ShoeProduct,
    ShoeProductImage,
    ShoeVariant,
)
from apps.catalog.models_vk import YMLFeedSnapshot
from apps.catalog.services import yml_feed

FEED_URL = "/api/catalog/export/yml/catalog.yml"


@pytest.fixture(autouse=True)
def feed_storage(settings, tmp_path):
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path), "base_url": "/media/"},
        },
        # Админка в тестах — без манифеста collectstatic.
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    settings.FRONTEND_SITE_URL = "https://mudaroba.example"
    settings.SOURCE_OFFER_CATALOG_PROJECTION_ENABLED = False
    return tmp_path


@pytest.fixture
def rub_rate(monkeypatch):
    """Лира → рубль ×3 с наценкой 10 %, без настоящих курсов."""
    from apps.catalog.utils.currency_converter import currency_converter

    def convert(amount, from_currency, to_currency, apply_margin=True):
        converted = Decimal(str(amount)) * 3
        return amount, converted, converted * Decimal("1.1")

    monkeypatch.setattr(currency_converter, "convert_price", convert)


def _category(slug, parent=None):
    return Category.objects.create(name=slug.title(), slug=f"{slug}-{uuid4().hex[:8]}", parent=parent)


def _shoe(category, *, variants=2, with_attribute=True):
    domain = ShoeProduct.objects.create(
        name=f"Shoe {uuid4().hex[:6]}",
        slug=f"shoe-{uuid4().hex}",
        description="Кожаные кроссовки",
        category=category,
        price=Decimal("100.00"),
        currency="TRY",
        is_available=True,
    )
    domain.refresh_from_db()
    # bulk_create — без сигнала, который скачивает внешние картинки.
    ShoeProductImage.objects.bulk_create(
        [ShoeProductImage(product=domain, image_url="https://cdn.example/gallery.jpg")]
    )
    for i in range(variants):
        variant = ShoeVariant.objects.create(
            product=domain,
            name=f"Variant {i}",
            slug=f"shoe-variant-{uuid4().hex}",
            color=f"Цвет {i}",
            size="42",
            price=Decimal("200.00"),
            currency="TRY",
            is_available=True,
        )
        ShoeVariant.objects.filter(pk=variant.pk).update(main_image=f"/media/v{variant.pk}.jpg")
    if with_attribute:
        key, created = GlobalAttributeKey.objects.get_or_create(slug="material-yml-test")
        if created:
            GlobalAttributeKeyTranslation.objects.create(key_obj=key, locale="ru", name="Материал")
        ProductAttributeValue.objects.create(content_object=domain, attribute_key=key, value="Кожа")
    return domain.base_product


def _parse(chunks):
    return ET.fromstring("".join(chunks).encode("utf-8"))


def _offers(root):
    return root.find("shop").find("offers").findall("offer")


@pytest.mark.django_db
def test_feed_builds_one_offer_per_variant_with_rub_prices_and_specs(rub_rate):
    root_cat = _category("shoes")
    product = _shoe(root_cat)

    root = _parse(yml_feed.iter_yml_feed(root_cat.slug))
    offers = _offers(root)

    variants = list(product.shoe_item.variants.all())
    assert [o.attrib["id"] for o in offers] == [f"{product.id}v{v.id}" for v in variants]
    first = offers[0]
    # 200 TRY → ×3 → +10 % наценки: как на сайте, а не «200 RUB».
    assert first.findtext("price") == "660"
    assert first.findtext("currencyId") == "RUB"
    pictures = [p.text for p in first.findall("picture")]
    assert pictures[0].startswith("https://mudaroba.example/media/v")
    assert "https://cdn.example/gallery.jpg" in pictures
    description = first.findtext("description")
    assert f"Цвет: {variants[0].color}" in description
    assert "Материал: Кожа" in description
    assert first.findtext("url") == f"https://mudaroba.example/product/shoes/{product.slug}"


@pytest.mark.django_db
def test_feed_query_count_does_not_grow_with_products(rub_rate):
    root_cat = _category("shoes")
    _shoe(root_cat)
    list(yml_feed.iter_yml_feed(root_cat.slug))  # прогрев кэшей ContentType и т.п.

    with CaptureQueriesContext(connection) as small:
        list(yml_feed.iter_yml_feed(root_cat.slug))

    for _ in range(4):
        _shoe(root_cat)
    with CaptureQueriesContext(connection) as large:
        list(yml_feed.iter_yml_feed(root_cat.slug))

    assert len(large) == len(small)


@pytest.mark.django_db
def test_category_feed_includes_subcategories_only(rub_rate):
    root_cat = _category("shoes")
    child = _category("sneakers", parent=root_cat)
    other = _category("bags")
    in_child = _shoe(child, variants=0)
    _shoe(other, variants=0)

    offers = _offers(_parse(yml_feed.iter_yml_feed(root_cat.slug)))

    assert [o.attrib["id"] for o in offers] == [str(in_child.id)]


@pytest.mark.django_db
def test_generate_feed_file_switches_snapshot_and_removes_old_file(rub_rate, feed_storage):
    root_cat = _category("shoes")
    _shoe(root_cat, variants=1)

    first = yml_feed.generate_feed_file(root_cat.slug)
    old_path = feed_storage / first.file.name
    assert old_path.exists()
    assert first.offers_count == 1

    _shoe(root_cat, variants=0)
    second = yml_feed.generate_feed_file(root_cat.slug)

    assert second.pk == first.pk
    assert second.offers_count == 2
    assert not old_path.exists()
    assert len(_offers(ET.parse(feed_storage / second.file.name).getroot())) == 2


@pytest.mark.django_db
def test_endpoint_serves_prepared_file_with_etag(rub_rate):
    root_cat = _category("shoes")
    product = _shoe(root_cat, variants=0)
    yml_feed.generate_feed_file(root_cat.slug)
    client = APIClient()

    response = client.get(FEED_URL, {"category": root_cat.slug})

    assert response.status_code == 200
    assert response["Content-Type"] == "application/xml"
    body = b"".join(response.streaming_content)
    assert int(response["Content-Length"]) == len(body)
    assert [o.attrib["id"] for o in _offers(ET.fromstring(body))] == [str(product.id)]

    cached = client.get(FEED_URL, {"category": root_cat.slug}, HTTP_IF_NONE_MATCH=response["ETag"])
    assert cached.status_code == 304


@pytest.mark.django_db
def test_endpoint_without_prepared_file_asks_to_generate(monkeypatch):
    calls = []
    from apps.catalog import tasks

    monkeypatch.setattr(tasks.generate_yml_feeds, "delay", lambda: calls.append(1))
    client = APIClient()

    first = client.get(FEED_URL)
    second = client.get(FEED_URL)

    assert first.status_code == second.status_code == 503
    assert first["Retry-After"] == "600"
    assert calls == [1]  # повторные запросы не плодят задачи


@pytest.mark.django_db
def test_endpoint_streams_subcategory_on_the_fly(rub_rate):
    root_cat = _category("shoes")
    child = _category("sneakers", parent=root_cat)
    product = _shoe(child, variants=0)

    response = APIClient().get(FEED_URL, {"category": child.slug})

    assert response.status_code == 200
    body = b"".join(response.streaming_content)
    assert [o.attrib["id"] for o in _offers(ET.fromstring(body))] == [str(product.id)]
    assert not YMLFeedSnapshot.objects.exists()


@pytest.mark.django_db
def test_generate_task_builds_roots_and_full_catalog(rub_rate):
    from apps.catalog.tasks import generate_yml_feeds

    root_cat = _category("shoes")
    _shoe(root_cat, variants=0)

    result = generate_yml_feeds()

    assert result[root_cat.slug] == 1
    assert result["catalog"] >= 1
    assert set(YMLFeedSnapshot.objects.values_list("category_slug", flat=True)) >= {"", root_cat.slug}


@pytest.fixture
def staff_client(client):
    user = get_user_model().objects.create_superuser(
        username=f"admin-{uuid4().hex[:6]}", email=f"{uuid4().hex[:6]}@example.com", password="x" * 20
    )
    client.force_login(user)
    return client


CHANGELIST = "/admin/catalog/vkcategorymapping/"


@pytest.mark.django_db
def test_admin_changelist_lists_feeds_by_root_slug(staff_client):
    Category.objects.get_or_create(slug="medical-equipment", defaults={"name": "Медтехника"})

    response = staff_client.get(CHANGELIST)

    assert response.status_code == 200
    content = response.content.decode()
    assert "catalog.yml?category=medical-equipment" in content
    assert "ещё не собран" in content


@pytest.mark.django_db
def test_admin_photo_sync_is_queued_by_post_only(staff_client, settings, monkeypatch):
    from apps.catalog import tasks

    calls = []
    monkeypatch.setattr(tasks.sync_vk_photos_task, "delay", lambda category=None: calls.append(category))
    settings.VK_USER_TOKEN = "user-token"
    settings.VK_GROUP_ID = 1

    staff_client.get(f"{CHANGELIST}sync-photos/shoes/")
    response = staff_client.post(f"{CHANGELIST}sync-photos/shoes/")

    assert response.status_code == 302
    assert response["Location"] == CHANGELIST
    assert calls == ["shoes"]


@pytest.mark.django_db
def test_admin_photo_sync_without_token_is_not_queued(staff_client, settings, monkeypatch):
    from apps.catalog import tasks

    calls = []
    monkeypatch.setattr(tasks.sync_vk_photos_task, "delay", lambda category=None: calls.append(category))
    settings.VK_USER_TOKEN = ""

    response = staff_client.post(f"{CHANGELIST}sync-photos/", follow=True)

    assert calls == []
    assert "VK_USER_TOKEN" in response.content.decode()


@pytest.mark.django_db
def test_sync_vk_photos_category_includes_subcategories(settings, monkeypatch):
    from apps.catalog.management.commands import sync_vk_photos

    root_cat = _category("shoes")
    child = _category("sneakers", parent=root_cat)
    in_child = Product.objects.create(name="In child", slug=f"in-child-{uuid4().hex}", category=child)
    elsewhere = Product.objects.create(name="Elsewhere", slug=f"elsewhere-{uuid4().hex}", category=_category("bags"))
    Product.objects.filter(pk__in=[in_child.pk, elsewhere.pk]).update(main_image="https://cdn.example/a.jpg")

    class FakeSync:
        def __init__(self, token, group_id):
            pass

        def get_all_market_items(self):
            return [
                {"id": 1, "external_id": str(in_child.id), "title": "a"},
                {"id": 2, "external_id": str(elsewhere.id), "title": "b"},
            ]

    monkeypatch.setattr(sync_vk_photos, "VKMarketSync", FakeSync)
    settings.VK_USER_TOKEN = "user-token"
    settings.VK_GROUP_ID = 1
    out = io.StringIO()

    call_command("sync_vk_photos", category=root_cat.slug, dry_run=True, stdout=out)

    output = out.getvalue()
    assert f"[{in_child.id}]" in output
    assert f"[{elsewhere.id}]" not in output
