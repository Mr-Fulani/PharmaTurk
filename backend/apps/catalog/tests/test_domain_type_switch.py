"""Смена типа товара: медиа переезжают в новую доменную запись, прежняя уходит из выдачи.

Инцидент 21.10: косметичку Massimo Dutti (Product 26178) парсер сохранил одеждой
(ClothingProduct с 5 фото в варианте). В админке тип сменили на «Аксессуары»:
AccessoryProduct создался без галереи, а ClothingProduct остался в выдаче одежды.
"""

import json
from io import StringIO
from types import SimpleNamespace

import pytest
from django.core.management import CommandError, call_command
from rest_framework.test import APIClient

from apps.catalog.constants import get_or_create_root_category
from apps.catalog.domain_sync import ensure_domain_product_for_base
from apps.catalog.forms import ProductForm
from apps.catalog.models import (
    AccessoryProduct,
    Category,
    ClothingProduct,
    ClothingProductImage,
    ClothingVariant,
    ClothingVariantImage,
    ClothingVariantSize,
    Product,
    ShoeProduct,
)

pytestmark = pytest.mark.django_db

PHOTOS = [f"https://cdn.mudaroba.com/products/clothing/variants/makyaj/{i}.jpg" for i in range(5)]


@pytest.fixture(autouse=True)
def no_media_download(monkeypatch):
    monkeypatch.setattr("apps.catalog.signals._download_url_to_file", lambda url: None)


@pytest.fixture
def bag():
    """Товар в состоянии после парсинга: одежда, 5 фото в варианте «SİYAH»."""
    clothing = get_or_create_root_category("clothing")
    accessories = get_or_create_root_category("accessories")
    mens_bags = Category.objects.create(name="Мужские сумки", slug="mens-bags", parent=accessories)
    product = Product.objects.create(
        name="Büyük napa deri makyaj çantası",
        slug="buyuk-napa-deri-makyaj-cantas-massimodutti-69539551",
        product_type="clothing",
        category=clothing,
        price=7600,
        currency="TRY",
        external_id="massimodutti-69539551",
        main_image=PHOTOS[0],
    )
    clothing_item = ClothingProduct.objects.get(base_product=product)
    variant = ClothingVariant.objects.create(
        product=clothing_item, name="Büyük napa deri makyaj çantası - SİYAH", color="SİYAH",
        external_id="massimodutti-variant-69539551-700",
    )
    ClothingVariantSize.objects.create(variant=variant, size="01")
    for index, url in enumerate(PHOTOS):
        ClothingVariantImage.objects.create(
            variant=variant, image_url=url, image_file=url.split("cdn.mudaroba.com/")[1],
            sort_order=index, is_main=index == 0,
        )
    return SimpleNamespace(product=product, clothing_item=clothing_item, variant=variant, mens_bags=mens_bags)


def _switch_to_accessories(bag):
    bag.product.product_type = "accessories"
    bag.product.category = bag.mens_bags
    bag.product.save()


def test_type_switch_moves_variant_photos_to_accessory_gallery(bag):
    _switch_to_accessories(bag)

    accessory = AccessoryProduct.objects.get(base_product=bag.product)
    gallery = list(accessory.gallery_images.order_by("sort_order"))
    assert [row.image_url for row in gallery] == PHOTOS
    assert [row.image_file.name for row in gallery] == [url.split("cdn.mudaroba.com/")[1] for url in PHOTOS]
    assert [row.is_main for row in gallery] == [True, False, False, False, False]

    bag.clothing_item.refresh_from_db()
    bag.product.refresh_from_db()
    assert bag.clothing_item.is_active is False
    assert (bag.product.product_type, bag.product.is_active) == ("accessories", True)
    # Ссылки на файлы у прежней записи остаются: cleanup_orphaned_media их не тронет.
    assert ClothingVariantImage.objects.filter(variant=bag.variant).count() == 5


def test_retired_clothing_record_leaves_clothing_listing(bag):
    client = APIClient()
    assert client.get("/api/catalog/clothing/products", {"search": "makyaj"}).json()["count"] == 1

    _switch_to_accessories(bag)

    assert client.get("/api/catalog/clothing/products", {"search": "makyaj"}).json()["count"] == 0


def test_saving_retired_record_does_not_revert_or_disable_product(bag):
    _switch_to_accessories(bag)
    bag.clothing_item.refresh_from_db()

    bag.clothing_item.name = "Правка в админке одежды"
    bag.clothing_item.save()

    bag.product.refresh_from_db()
    assert (bag.product.product_type, bag.product.is_active) == ("accessories", True)
    assert bag.product.name == "Büyük napa deri makyaj çantası"


def test_is_active_follows_product_only_on_current_record(bag):
    _switch_to_accessories(bag)

    bag.product.is_active = False
    bag.product.save()
    assert AccessoryProduct.objects.get(base_product=bag.product).is_active is False

    bag.product.is_active = True
    bag.product.save()
    assert AccessoryProduct.objects.get(base_product=bag.product).is_active is True
    bag.clothing_item.refresh_from_db()
    assert bag.clothing_item.is_active is False


def test_switch_to_type_with_variants_copies_variants(bag):
    bag.product.product_type = "shoes"
    bag.product.category = get_or_create_root_category("shoes")
    bag.product.save()

    shoe = ShoeProduct.objects.get(base_product=bag.product)
    variant = shoe.variants.get()
    assert (variant.color, variant.external_id) == ("SİYAH", "massimodutti-variant-69539551-700")
    assert [row.image_url for row in variant.images.order_by("sort_order")] == PHOTOS
    assert list(variant.sizes.values_list("size", flat=True)) == ["01"]
    bag.clothing_item.refresh_from_db()
    assert bag.clothing_item.is_active is False


def test_switching_back_reactivates_record_without_duplicate_photos(bag):
    _switch_to_accessories(bag)

    bag.product.product_type = "clothing"
    bag.product.category = get_or_create_root_category("clothing")
    bag.product.save()

    bag.clothing_item.refresh_from_db()
    assert bag.clothing_item.is_active is True
    assert AccessoryProduct.objects.get(base_product=bag.product).is_active is False
    # Фото уже в варианте — в общую галерею одежды не дублируются.
    assert not ClothingProductImage.objects.filter(product=bag.clothing_item).exists()


class _TypeCategoryForm(ProductForm):
    class Meta(ProductForm.Meta):
        fields = ("product_type", "category")


def test_admin_category_of_other_type_switches_product_type(bag):
    form = _TypeCategoryForm(
        instance=bag.product, data={"product_type": "clothing", "category": bag.mens_bags.pk},
    )

    assert form.is_valid(), form.errors
    form.save()

    bag.product.refresh_from_db()
    assert bag.product.product_type == "accessories"
    assert AccessoryProduct.objects.get(base_product=bag.product).gallery_images.count() == 5


def test_admin_explicit_type_choice_is_kept(bag):
    form = _TypeCategoryForm(
        instance=bag.product, data={"product_type": "jewelry", "category": bag.mens_bags.pk},
    )

    assert form.is_valid(), form.errors
    assert form.cleaned_data["product_type"] == "jewelry"


def _legacy_state(bag):
    """Как на проде до исправления: тип сменён, обе доменные записи активны."""
    Product.objects.filter(pk=bag.product.pk).update(product_type="accessories", category=bag.mens_bags)
    ensure_domain_product_for_base(Product.objects.get(pk=bag.product.pk))


def test_command_dry_run_reports_without_changes(bag):
    _legacy_state(bag)
    out = StringIO()

    call_command("retire_stale_domain_records", "--product", str(bag.product.pk), stdout=out)

    text = out.getvalue()
    assert "Товаров с несколькими доменными записями: 1" in text
    assert "активна (товар виден в чужой выдаче): 1" in text
    assert f"ClothingProduct {bag.clothing_item.pk} (активна: да)" in text
    assert "фото 5, вариантов 0" in text
    bag.clothing_item.refresh_from_db()
    assert bag.clothing_item.is_active is True
    assert AccessoryProduct.objects.get(base_product=bag.product).gallery_images.count() == 0


def test_command_apply_requires_backup(bag):
    _legacy_state(bag)

    with pytest.raises(CommandError):
        call_command("retire_stale_domain_records", "--product", str(bag.product.pk), "--apply", stdout=StringIO())


def test_command_apply_moves_photos_and_writes_backup(bag, tmp_path):
    _legacy_state(bag)
    backup = tmp_path / "stale.json"

    call_command(
        "retire_stale_domain_records", "--product", str(bag.product.pk),
        "--apply", "--backup", str(backup), stdout=StringIO(),
    )

    accessory = AccessoryProduct.objects.get(base_product=bag.product)
    assert accessory.gallery_images.count() == 5
    bag.clothing_item.refresh_from_db()
    bag.product.refresh_from_db()
    assert bag.clothing_item.is_active is False
    assert (bag.product.product_type, bag.product.is_active) == ("accessories", True)
    saved = json.loads(backup.read_text(encoding="utf-8"))
    assert saved == [{
        "product": bag.product.pk,
        "product_type": "accessories",
        "current": {
            "model": "AccessoryProduct", "pk": accessory.pk,
            "gallery_pks_before": [], "variant_pks_before": [],
        },
        "stale": [{"model": "ClothingProduct", "pk": bag.clothing_item.pk, "is_active": True}],
    }]

    # Повторный запуск ничего не дублирует.
    call_command(
        "retire_stale_domain_records", "--product", str(bag.product.pk),
        "--apply", "--backup", str(tmp_path / "again.json"), stdout=StringIO(),
    )
    assert accessory.gallery_images.count() == 5
