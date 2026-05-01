import pytest

from apps.catalog.models import Category
from apps.catalog.serializers import CategorySerializer


@pytest.mark.django_db
def test_category_seo_fallbacks_include_category_context_and_card_media():
    parent = Category.objects.create(
        name="Одежда",
        slug="clothing-parent",
        card_media_external_url="https://cdn.example.com/categories/clothing.jpg",
    )
    category = Category.objects.create(
        name="Футболки",
        slug="futbolki",
        parent=parent,
    )

    assert category.get_effective_meta_title() == "Футболки | Одежда | Mudaroba"
    assert "Каталог товаров категории Футболки" in category.get_effective_meta_description()
    assert "Футболки" in category.get_effective_meta_keywords()
    assert category.get_effective_og_image_url() == "https://cdn.example.com/categories/clothing.jpg"


@pytest.mark.django_db
def test_category_serializer_returns_generated_seo_fields_when_db_fields_are_blank():
    category = Category.objects.create(
        name="Услуги",
        slug="uslugi",
        description="Услуги различного назначения",
        card_media_external_url="https://cdn.example.com/categories/services.png",
    )

    data = CategorySerializer(category).data

    assert data["meta_title"] == "Услуги | Mudaroba"
    assert data["meta_description"] == "Услуги различного назначения"
    assert data["og_title"] == "Услуги | Mudaroba"
    assert data["og_description"] == "Услуги различного назначения"
    assert data["og_image_url"] == "https://cdn.example.com/categories/services.png"


@pytest.mark.django_db
def test_category_save_persists_og_image_url_from_category_preview_when_blank():
    category = Category.objects.create(
        name="Украшения",
        slug="jewelry",
        card_media_external_url="https://cdn.example.com/categories/jewelry.webp",
        og_image_url="",
    )

    category.refresh_from_db()

    assert category.og_image_url == "https://cdn.example.com/categories/jewelry.webp"
