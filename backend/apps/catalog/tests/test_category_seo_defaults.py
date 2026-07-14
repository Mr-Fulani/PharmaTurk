import pytest
from rest_framework.test import APIRequestFactory

from apps.catalog.models import (
    Category,
    CategoryType,
    Service,
    ServicePortfolioItem,
    ServicePortfolioMedia,
    ServiceTranslation,
)
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


@pytest.mark.django_db
def test_category_serializer_includes_service_portfolio_items():
    # Портфолио отдаётся только для категорий услуг (тип uslugi)
    uslugi_type, _ = CategoryType.objects.get_or_create(slug="uslugi", defaults={"name": "Услуги"})
    category = Category.objects.create(
        name="Ремонт",
        slug="repair-services",
        category_type=uslugi_type,
    )
    service = Service.objects.create(
        name="Ремонт ванной",
        slug="bathroom-repair",
        category=category,
    )
    item = ServicePortfolioItem.objects.create(
        category=category,
        service=service,
        title="Капремонт ванной комнаты",
        result_summary="12 дней",
        alt_text="Капремонт ванной комнаты",
    )
    # Картинки кейса живут в отдельной модели media_items с плашками до/после
    ServicePortfolioMedia.objects.create(
        portfolio_item=item,
        badge="before",
        media_url="https://cdn.example.com/portfolio/bathroom-before.jpg",
        sort_order=0,
    )
    ServicePortfolioMedia.objects.create(
        portfolio_item=item,
        badge="after",
        media_url="https://cdn.example.com/portfolio/bathroom-after.jpg",
        sort_order=1,
    )

    data = CategorySerializer(category).data

    assert len(data["portfolio_items"]) == 1
    assert data["portfolio_items"][0]["title"] == "Капремонт ванной комнаты"
    assert data["portfolio_items"][0]["service_slug"] == "bathroom-repair"
    media = data["portfolio_items"][0]["media_items"]
    assert [(m["badge"], m["media_url"]) for m in media] == [
        ("before", "https://cdn.example.com/portfolio/bathroom-before.jpg"),
        ("after", "https://cdn.example.com/portfolio/bathroom-after.jpg"),
    ]


@pytest.mark.django_db
def test_category_serializer_excludes_inactive_portfolio_items_and_inactive_services():
    uslugi_type, _ = CategoryType.objects.get_or_create(slug="uslugi", defaults={"name": "Услуги"})
    category = Category.objects.create(
        name="Ремонт",
        slug="repair-portfolio-visibility",
        category_type=uslugi_type,
    )
    active_service = Service.objects.create(
        name="Активная услуга",
        slug="active-portfolio-service",
        category=category,
    )
    inactive_service = Service.objects.create(
        name="Неактивная услуга",
        slug="inactive-portfolio-service",
        category=category,
        is_active=False,
    )
    visible_item = ServicePortfolioItem.objects.create(
        category=category,
        service=active_service,
        title="Активный кейс",
    )
    ServicePortfolioItem.objects.create(
        category=category,
        service=active_service,
        title="Неактивный кейс",
        is_active=False,
    )
    ServicePortfolioItem.objects.create(
        category=category,
        service=inactive_service,
        title="Кейс неактивной услуги",
    )

    data = CategorySerializer(category).data

    assert [item["id"] for item in data["portfolio_items"]] == [visible_item.id]


@pytest.mark.django_db
def test_category_serializer_localizes_service_portfolio_items_for_english():
    uslugi_type, _ = CategoryType.objects.get_or_create(slug="uslugi", defaults={"name": "Услуги"})
    category = Category.objects.create(
        name="Услуги",
        slug="services-root",
        category_type=uslugi_type,
    )
    service = Service.objects.create(
        name="Миграционная консультация",
        slug="migration-consultation",
        category=category,
    )
    ServiceTranslation.objects.create(
        service=service,
        locale="en",
        name="Migration consultation",
        description="Support with documents and legal steps.",
    )
    ServicePortfolioItem.objects.create(
        category=category,
        service=service,
        title="Помощь с ВНЖ в Турции",
        title_en="Residence permit support in Turkey",
        description="Подготовили пакет документов и маршрут подачи.",
        description_en="We prepared the document package and filing roadmap.",
        result_summary="Подача без ошибок",
        result_summary_en="Error-free application",
        alt_text="Консультация по ВНЖ в Турции",
        alt_text_en="Residence permit consultation in Turkey",
    )

    request = APIRequestFactory().get("/", HTTP_ACCEPT_LANGUAGE="en")
    request.LANGUAGE_CODE = "en"

    data = CategorySerializer(category, context={"request": request}).data

    assert data["portfolio_items"][0]["title"] == "Residence permit support in Turkey"
    assert data["portfolio_items"][0]["description"] == "We prepared the document package and filing roadmap."
    assert data["portfolio_items"][0]["result_summary"] == "Error-free application"
    assert data["portfolio_items"][0]["alt_text"] == "Residence permit consultation in Turkey"
    assert data["portfolio_items"][0]["service_name"] == "Migration consultation"
