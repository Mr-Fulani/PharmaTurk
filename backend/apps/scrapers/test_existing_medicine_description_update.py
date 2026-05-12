import pytest
from decimal import Decimal

from apps.catalog.models import Product
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.services import ScraperIntegrationService


def test_ilacfiyati_existing_medicine_description_can_be_replaced_with_full_tabs():
    service = ScraperIntegrationService.__new__(ScraperIntegrationService)
    product = Product(
        product_type="medicines",
        description="İLAÇ DURUMU: AKTİF\n\nÖzet:\nKULLANMA TALİMATI\nAğızdan alınır.",
    )
    scraped = ScrapedProduct(
        name="LASIRIN",
        source="ilacfiyati",
        description=(
            "İLAÇ DURUMU: AKTİF\n\n"
            "Özet:\nKULLANMA TALİMATI\nAğızdan alınır.\n\n"
            "Ne İçin Kullanılır:\nAlerjik hastalıklarda kullanılır.\n\n"
            "Kullanmadan Dikkat Edilecekler:\nDoktorunuza danışınız.\n\n"
            "Nasıl Kullanılır:\nDoktorunuzun söylediği şekilde kullanınız.\n\n"
            "Yan Etkileri:\nUyku hali görülebilir.\n\n"
            "Saklanması:\n25°C altındaki oda sıcaklığında saklayınız."
        ),
        attributes={"source_tabs": {"indications": {"text": "Alerjik hastalıklarda kullanılır."}}},
    )

    assert service._should_replace_existing_description(
        product,
        scraped,
        product.description,
        scraped.description,
    )


def test_ilacfiyati_existing_medicine_description_does_not_replace_ai_copy_without_richer_tabs():
    service = ScraperIntegrationService.__new__(ScraperIntegrationService)
    product = Product(
        product_type="medicines",
        description="LASIRIN 20 mg таблетка содержит биластин. Применяйте по назначению врача.",
    )
    scraped = ScrapedProduct(
        name="LASIRIN",
        source="ilacfiyati",
        description="İLAÇ DURUMU: AKTİF\n\nÖzet:\nKULLANMA TALİMATI",
        attributes={"source_tabs": {"summary": {"text": "KULLANMA TALİMATI"}}},
    )

    assert not service._should_replace_existing_description(
        product,
        scraped,
        product.description,
        scraped.description,
    )


@pytest.mark.django_db
def test_ilacfiyati_legacy_tab_external_id_is_repaired_instead_of_creating_duplicate():
    service = ScraperIntegrationService()
    existing = Product.objects.create(
        name="LASIRIN 20 MG TABLET (20 TABLET)",
        slug="lasirin-old",
        product_type="medicines",
        external_id="ilac-bilgileri",
        description="İLAÇ DURUMU: AKTİF",
    )
    scraped = ScrapedProduct(
        name="LASIRIN 20 MG TABLET (20 TABLET)",
        source="ilacfiyati",
        external_id="lasirin-20-mg-tablet-20-tablet",
        description=(
            "İLAÇ DURUMU: AKTİF\n\n"
            "Ne İçin Kullanılır:\nAlerjik hastalıklarda kullanılır."
        ),
        attributes={"source_tabs": {"indications": {"text": "Alerjik hastalıklarda kullanılır."}}},
    )

    action, product = service._process_single_product(None, scraped)

    existing.refresh_from_db()
    assert action == "updated"
    assert product.pk == existing.pk
    assert existing.external_id == "lasirin-20-mg-tablet-20-tablet"
    assert Product.objects.filter(name="LASIRIN 20 MG TABLET (20 TABLET)").count() == 1


@pytest.mark.django_db
def test_ilacfiyati_legacy_external_id_repair_does_not_depend_on_ai_slug_or_name():
    service = ScraperIntegrationService()
    existing = Product.objects.create(
        name="ЛАСИРИН 20 МГ таблетки",
        slug="lasirin-20-mg-tabletki",
        product_type="medicines",
        external_id="ilac-bilgileri",
        external_url="https://ilacfiyati.com/ilaclar/lasirin-20-mg-tablet-20-tablet/ilac-bilgileri",
        description="AI описание",
    )
    scraped = ScrapedProduct(
        name="LASIRIN 20 MG TABLET (20 TABLET)",
        source="ilacfiyati",
        external_id="lasirin-20-mg-tablet-20-tablet",
        url="https://ilacfiyati.com/ilaclar/lasirin-20-mg-tablet-20-tablet",
        description="İLAÇ DURUMU: AKTİF",
    )

    action, product = service._process_single_product(None, scraped)

    existing.refresh_from_db()
    assert action == "updated"
    assert product.pk == existing.pk
    assert existing.external_id == "lasirin-20-mg-tablet-20-tablet"
    assert Product.objects.filter(external_id="lasirin-20-mg-tablet-20-tablet").count() == 1


@pytest.mark.django_db
def test_ilacfiyati_stub_with_empty_external_id_is_updated_by_source_url():
    service = ScraperIntegrationService()
    existing = Product.objects.create(
        name="BILASBIL 2,5 MG/ML ORAL COZELTI (120 ML)",
        slug="bilasbil-stub",
        product_type="medicines",
        external_id="",
        external_url="https://ilacfiyati.com/ilaclar/bilasbil-2-5-mg-ml-oral-cozelti-120-ml",
        description="",
    )
    scraped = ScrapedProduct(
        name="BILASBIL 2,5 MG/ML ORAL COZELTI (120 ML)",
        source="ilacfiyati",
        external_id="bilasbil-2-5-mg-ml-oral-cozelti-120-ml",
        url="https://ilacfiyati.com/ilaclar/bilasbil-2-5-mg-ml-oral-cozelti-120-ml",
        description="İLAÇ DURUMU: AKTİF",
    )

    action, product = service._process_single_product(None, scraped)

    existing.refresh_from_db()
    assert action == "updated"
    assert product.pk == existing.pk
    assert existing.external_id == "bilasbil-2-5-mg-ml-oral-cozelti-120-ml"
    assert Product.objects.filter(name="BILASBIL 2,5 MG/ML ORAL COZELTI (120 ML)").count() == 1


@pytest.mark.django_db
def test_ilacfiyati_stub_update_keeps_base_fields_after_medicine_domain_save():
    service = ScraperIntegrationService()
    existing = Product.objects.create(
        name="BILASBIL 2,5 MG/ML ORAL COZELTI (120 ML)",
        slug="bilasbil-stub",
        product_type="medicines",
        external_id="bilasbil-2-5-mg-ml-oral-cozelti-120-ml",
        external_url="https://ilacfiyati.com/ilaclar/bilasbil-2-5-mg-ml-oral-cozelti-120-ml",
        description="",
        price=None,
        external_data={"source": "ilacfiyati", "is_stub": True},
    )
    # Прогреваем related-object cache: именно так старая доменная заглушка могла
    # перетереть свежие Product-поля при save() MedicineProduct.
    assert existing.medicine_item.pk

    scraped = ScrapedProduct(
        name="BILASBIL 2,5 MG/ML ORAL COZELTI (120 ML)",
        source="ilacfiyati",
        external_id="bilasbil-2-5-mg-ml-oral-cozelti-120-ml",
        url="https://ilacfiyati.com/ilaclar/bilasbil-2-5-mg-ml-oral-cozelti-120-ml",
        description="İLAÇ DURUMU: AKTİF\n\nİLAÇ FİYATI: 167,20 TL\n\nNFC KODU: DGA",
        price=167.2,
        currency="TRY",
        attributes={
            "active_ingredient": "Bilastin",
            "barcode": "8699569590149",
            "atc_code": "R06AX29",
            "nfc_code": "DGA",
            "source_tabs": {"sgk_equivalents": {"text": "BILASBIL"}},
        },
    )

    action, product = service._process_single_product(None, scraped)

    existing.refresh_from_db()
    medicine = existing.medicine_item
    assert action == "updated"
    assert product.pk == existing.pk
    assert existing.price == Decimal("167.20")
    assert existing.currency == "TRY"
    assert existing.description == scraped.description
    assert existing.external_data["is_stub"] is False
    assert existing.external_data["attributes"]["nfc_code"] == "DGA"
    assert medicine.price == Decimal("167.20")
    assert medicine.currency == "TRY"
    assert medicine.description == scraped.description
    assert medicine.nfc_code == "DGA"
