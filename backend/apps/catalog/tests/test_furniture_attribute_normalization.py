import pytest
from django.utils import translation

from apps.catalog.models import Category, FurnitureProduct
from apps.catalog.serializers import FurnitureProductSerializer
from apps.catalog.services.furniture_attributes import (
    build_furniture_dynamic_attributes,
    sync_furniture_dynamic_attributes,
)


RAW_ATTRIBUTES = {
    "furniture_type": "çift kişilik baza",
    "material": (
        "<p>Orta kiriş:Galvanizli çelik</p>"
        "<p>Panel:MDF ve sunta, Plastik kenar</p>"
        "<p>Ara halkası:Masif çam ağacı</p>"
    ),
    "dimensions": (
        "<p>Karyola ayak ucu yüksekliği: 66 cm</p>"
        "<p>Karyola başlığı yüksekliği: 120 cm</p>"
        "<p>Uzunluk: 211 cm</p>"
        "<p>Yatak uzunluğu: 200 cm</p>"
        "<p>Yatak genişliği: 180 cm</p>"
        "<p>Genişlik: 194 cm</p>"
    ),
}


def test_build_furniture_attributes_localizes_type_material_and_dimensions():
    rows = {row["slug"]: row for row in build_furniture_dynamic_attributes(RAW_ATTRIBUTES)}

    assert rows["furniture-type"]["value_ru"] == "Двуспальное основание кровати"
    assert rows["furniture-type"]["value_en"] == "Double bed base"
    assert rows["material"]["value_ru"] == "МДФ, ДСП, массив сосны, сталь, пластик"
    assert rows["material"]["value_en"] == "MDF, Particleboard, solid pine, steel, plastic"
    assert rows["footboard-height"]["value_ru"] == "66 см"
    assert rows["headboard-height"]["value_en"] == "120 cm"
    assert rows["mattress-width"]["value_ru"] == "180 см"
    assert rows["width"]["value_en"] == "194 cm"


@pytest.mark.django_db
def test_sync_furniture_attributes_is_idempotent_and_preserves_existing_values():
    category = Category.objects.create(name="Основания кроватей", slug="test-bed-bases")
    product = FurnitureProduct.objects.create(
        name="TONSTAD",
        slug="test-tonstad-attributes",
        category=category,
    )

    assert sync_furniture_dynamic_attributes(product, RAW_ATTRIBUTES) == 8
    assert sync_furniture_dynamic_attributes(product, RAW_ATTRIBUTES) == 0

    material = product.dynamic_attributes.get(attribute_key__slug="material")
    material.value_ru = "Ручное значение"
    material.save(update_fields=["value_ru"])

    assert sync_furniture_dynamic_attributes(product, RAW_ATTRIBUTES) == 0
    material.refresh_from_db()
    assert material.value_ru == "Ручное значение"


@pytest.mark.django_db
def test_furniture_api_uses_localized_dynamic_values_and_hides_raw_turkish_fallback():
    category = Category.objects.create(name="Основания кроватей", slug="test-bed-bases-api")
    product = FurnitureProduct.objects.create(
        name="TONSTAD",
        slug="test-tonstad-api-attributes",
        category=category,
    )
    sync_furniture_dynamic_attributes(product, RAW_ATTRIBUTES)

    with translation.override("en"):
        data = FurnitureProductSerializer(product).data
    rows = {row["key"]: row["value"] for row in data["dynamic_attributes"]}

    assert rows["furniture-type"] == "Double bed base"
    assert rows["headboard-height"] == "120 cm"
