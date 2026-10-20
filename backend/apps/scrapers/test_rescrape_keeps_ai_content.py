"""Повторный парсинг не перетирает тексты, которые сделал AI или менеджер."""

import pytest

from apps.ai.models import AIApplicationStatus, AIProcessingLog, AIProcessingStatus
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.ownership import SOURCE_CHANGED_KEY, SOURCE_DESCRIPTION_KEY, SOURCE_NAME_KEY
from apps.ai.services.result_applier import AIResultApplier
from apps.catalog.models import GlobalAttributeKey, MedicineProduct, Product
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.services import ScraperIntegrationService, scraping_in_progress_context

pytestmark = pytest.mark.django_db

URL = "https://ilacfiyati.com/ilaclar/majezik-100-mg-15-film-tablet"
TABS = (
    "İLAÇ DURUMU: AKTİF\n\nÖzet:\nKULLANMA TALİMATI\n\n"
    "Ne İçin Kullanılır:\nAğrı ve iltihapta kullanılır. " + "Uzun kaynak metin. " * 60 + "\n\n"
    "Kullanmadan Dikkat Edilecekler:\nDoktorunuza danışınız.\n\n"
    "Nasıl Kullanılır:\nGünde 2 kez 100 mg alınız.\n\n"
    "Yan Etkileri:\nMide bulantısı görülebilir.\n\n"
    "Saklanması:\n25°C altında saklayınız."
)


def _scraped(description=TABS, price=204.49):
    return ScrapedProduct(
        name="MAJEZIK 100 MG 15 FILM TABLET",
        source="ilacfiyati",
        external_id="majezik-100-mg-15-film-tablet",
        url=URL,
        description=description,
        price=price,
        currency="TRY",
        attributes={"source_tabs": {"indications": {"text": "Ağrı ve iltihapta kullanılır."}}},
    )


def _ai_processed_medicine():
    medicine = MedicineProduct.objects.create(
        name="MAJEZIK 100 MG 15 FILM TABLET",
        slug="majezik-100-mg-15-film-tablet",
        description="İLAÇ DURUMU: AKTİF\n\nÖzet:\nKULLANMA TALİMATI",
        external_id="majezik-100-mg-15-film-tablet",
        external_url=URL,
        price=180,
        currency="TRY",
    )
    medicine.refresh_from_db()
    product = medicine.base_product
    key, _ = GlobalAttributeKey.objects.get_or_create(slug="material", defaults={"sort_order": 1})
    medicine.dynamic_attributes.create(attribute_key=key, value="AI значение", value_ru="AI значение", value_en="AI value")
    AIResultApplier().apply_to_product(
        product,
        {
            "generated_title": "Маджезик 100 мг, 15 таблеток",
            "generated_description": "Справочное описание от AI.",
            "generated_seo_title": "AI SEO",
            "translations": {
                "ru": {"name": "Маджезик 100 мг", "description": "AI описание RU", "indications": "AI показания"},
                "en": {"name": "Majezik 100 mg", "description": "AI description EN"},
            },
        },
    )
    AIProcessingLog.objects.create(
        product=product,
        processing_type="full",
        status=AIProcessingStatus.APPROVED,
        application_status=AIApplicationStatus.APPLIED,
        input_data={},
    )
    product.refresh_from_db()
    return medicine, product


def test_rescrape_after_ai_keeps_ai_texts_and_flags_changed_source():
    medicine, product = _ai_processed_medicine()
    service = ScraperIntegrationService()

    service._update_existing_product(None, _scraped(), product)
    service._update_existing_product(None, _scraped(description=TABS + "\n\nYeni uyarı eklendi.", price=210), product)

    product.refresh_from_db()
    medicine.refresh_from_db()
    ru = medicine.translations.get(locale="ru")
    en = medicine.translations.get(locale="en")
    assert product.name == medicine.name == "Маджезик 100 мг, 15 таблеток"
    assert product.description == medicine.description == "Справочное описание от AI."
    assert medicine.meta_title == "AI SEO"
    assert medicine.slug == product.slug == "majezik-100-mg-15-film-tablet"
    assert (ru.name, ru.description, ru.indications) == ("Маджезик 100 мг", "AI описание RU", "AI показания")
    assert (en.name, en.description) == ("Majezik 100 mg", "AI description EN")
    attr = medicine.dynamic_attributes.get(attribute_key__slug="material")
    assert (attr.value_ru, attr.value_en) == ("AI значение", "AI value")
    # Сырые поля обновляются, исходник сохранён отдельно, смена исходника помечена.
    assert float(product.price) == 210
    assert product.external_data[SOURCE_DESCRIPTION_KEY].endswith("Yeni uyarı eklendi.")
    assert product.external_data[SOURCE_CHANGED_KEY]


def test_first_rescrape_after_ai_records_source_without_reprocess_flag():
    _medicine, product = _ai_processed_medicine()

    ScraperIntegrationService()._update_existing_product(None, _scraped(), product)

    product.refresh_from_db()
    assert product.external_data[SOURCE_DESCRIPTION_KEY] == TABS.strip()
    assert SOURCE_CHANGED_KEY not in product.external_data


def test_manager_text_is_not_replaced_by_longer_source_without_ai():
    product = Product.objects.create(
        name="MAJEZIK",
        slug="majezik-manager-text",
        product_type="medicines",
        description="Описание, которое написал менеджер.",
        external_id="majezik-100-mg-15-film-tablet",
        external_url=URL,
        external_data={"source": "ilacfiyati"},
    )

    ScraperIntegrationService()._update_existing_product(None, _scraped(), product)

    product.refresh_from_db()
    assert product.description == "Описание, которое написал менеджер."


def test_untouched_scraped_text_is_still_upgraded_to_full_tabs():
    product = Product.objects.create(
        name="MAJEZIK",
        slug="majezik-raw-text",
        product_type="medicines",
        description="İLAÇ DURUMU: AKTİF\n\nÖzet:\nKULLANMA TALİMATI",
        external_id="majezik-100-mg-15-film-tablet",
        external_url=URL,
        external_data={"source": "ilacfiyati"},
    )

    ScraperIntegrationService()._update_existing_product(None, _scraped(), product)

    product.refresh_from_db()
    assert product.description == TABS.strip()
    assert SOURCE_DESCRIPTION_KEY not in product.external_data  # совпадает с description — не дублируем


def test_ai_reprocessing_uses_stored_source_and_apply_clears_flag():
    _medicine, product = _ai_processed_medicine()
    product.external_data = {
        **product.external_data,
        SOURCE_DESCRIPTION_KEY: "Kaynak metin",
        SOURCE_CHANGED_KEY: "2026-10-18T00:00:00",
    }
    product.save()
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.result_applier = AIResultApplier()

    product.refresh_from_db()
    assert generator._collect_input_data(product)["raw_description"] == "Kaynak metin"

    log = AIProcessingLog.objects.create(
        product=product,
        processing_type="full",
        status=AIProcessingStatus.COMPLETED,
        input_data={},
        generated_title="Маджезик 100 мг, 15 таблеток",
        generated_description="Новое справочное описание от AI, учитывающее исходник.",
        extracted_attributes={"translations_data": {"ru": {"indications": "Новые показания"}}},
    )
    generator.apply_log_to_product(log)

    product.refresh_from_db()
    assert SOURCE_CHANGED_KEY not in product.external_data
    assert product.name == "Маджезик 100 мг, 15 таблеток"


def test_rescrape_records_turkish_source_name_without_touching_translated_name():
    # Прод 20.10.2026: у 103 лекарств name переведён прежней обработкой, а
    # парсер name существующего товара не пишет — оригинал кладётся в source_name.
    product = Product.objects.create(
        name="MAJEZIK 100 MG 15 ФИЛЬМ ТАБЛЕТКИ",
        slug="majezik-translated-name",
        product_type="medicines",
        external_id="majezik-100-mg-15-film-tablet",
        external_url=URL,
        external_data={"source": "ilacfiyati"},
    )

    ScraperIntegrationService()._update_existing_product(None, _scraped(), product)

    product.refresh_from_db()
    medicine = MedicineProduct.objects.get(base_product=product)
    assert product.name == "MAJEZIK 100 MG 15 ФИЛЬМ ТАБЛЕТКИ"
    assert product.external_data[SOURCE_NAME_KEY] == "MAJEZIK 100 MG 15 FILM TABLET"
    assert medicine.external_data[SOURCE_NAME_KEY] == "MAJEZIK 100 MG 15 FILM TABLET"


def test_rescrape_after_ai_keeps_ai_title_and_source_name():
    _medicine, product = _ai_processed_medicine()

    ScraperIntegrationService()._update_existing_product(None, _scraped(), product)

    product.refresh_from_db()
    assert product.name == "Маджезик 100 мг, 15 таблеток"
    assert product.external_data[SOURCE_NAME_KEY] == "MAJEZIK 100 MG 15 FILM TABLET"


def test_new_ilacfiyati_product_records_source_name():
    service = ScraperIntegrationService()

    with scraping_in_progress_context():
        _action, product = service._create_new_product(None, _scraped())

    product.refresh_from_db()
    assert product.external_data[SOURCE_NAME_KEY] == "MAJEZIK 100 MG 15 FILM TABLET"


def _clothing_with_ai_named_variant(slug):
    from apps.catalog.models import Category, ClothingVariant

    category = Category.objects.create(name=f"Одежда {slug}", slug=f"clothing-{slug}")
    product = Product.objects.create(
        name="Рубашка LCW",
        slug=slug,
        category=category,
        product_type="clothing",
        price=100,
        currency="TRY",
        external_id=f"lcw-{slug}",
        external_data={},
    )
    clothing = product.domain_item
    ClothingVariant.objects.create(
        product=clothing,
        name="Рубашка из льна - Чёрный",
        name_en="Linen shirt - Black",
        color="black",
        external_id=f"lcw-var-{slug}",
        price=100,
        currency="TRY",
    )
    return product, clothing


def _variant_spec(slug):
    return {
        "external_id": f"lcw-var-{slug}",
        "color": "black",
        "price": "120",
        "currency": "TRY",
        "external_url": "https://www.lcw.com/rubashka-o-1",
        "stock_quantity": 3,
        "is_available": True,
    }


def test_rescrape_keeps_ai_variant_names_but_updates_price():
    product, clothing = _clothing_with_ai_named_variant("ai-variant-names")
    AIProcessingLog.objects.create(
        product=product,
        processing_type="full",
        status=AIProcessingStatus.APPROVED,
        application_status=AIApplicationStatus.APPLIED,
        input_data={},
    )

    ScraperIntegrationService()._sync_fashion_variants(
        product, variants=[_variant_spec("ai-variant-names")]
    )

    variant = clothing.variants.get()
    assert (variant.name, variant.name_en) == ("Рубашка из льна - Чёрный", "Linen shirt - Black")
    assert variant.price == 120


def test_rescrape_refreshes_variant_names_without_ai_content():
    product, clothing = _clothing_with_ai_named_variant("plain-variant-names")

    ScraperIntegrationService()._sync_fashion_variants(
        product, variants=[_variant_spec("plain-variant-names")]
    )

    variant = clothing.variants.get()
    assert variant.name_en != "Linen shirt - Black"
