"""Автозапчасти: название, описание и SEO собирает код — модель не вызывается."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from apps.ai.models import AIProcessingStatus
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.result_applier import AIResultApplier
from apps.ai.services.rules.auto_part_vocab import PART_KINDS, find_kind, model_name, proper_name, translate_spec
from apps.ai.services.rules.auto_parts import (
    AutoPartKindUnknown,
    build_auto_part_titles,
    collect_auto_part_facts,
    run_auto_part_content,
)
from apps.catalog.models import AutoPartFitment, AutoPartNumber, AutoPartProduct, Brand, Category

SUBSECTIONS = (Path(__file__).parent / "aloparca_subsections.txt").read_text(encoding="utf-8").split()


def test_vocabulary_covers_every_source_subsection():
    """Все подразделы Aloparça на 24.11.2026 (sitemaps/categories.xml)."""
    assert len(SUBSECTIONS) > 300
    assert [slug for slug in SUBSECTIONS if slug not in PART_KINDS] == []


def test_vocabulary_values_are_russian_and_english():
    for slug, (ru, en) in PART_KINDS.items():
        assert ru and ru == ru.strip() and any("а" <= ch <= "я" or ch == "ё" for ch in ru.lower()), slug
        assert en and en[0].isupper() and en.isascii(), slug


def test_kind_is_found_by_turkish_title_then_by_section():
    assert find_kind("Fren Disk Balata") == ("тормозные колодки дисковые", "Disc Brake Pads")
    assert find_kind("Ateşleme Bujisi") == ("свеча зажигания", "Spark Plug")
    assert find_kind("Yeni Bir Parça", "Yağ Filtresi") == ("масляный фильтр", "Oil Filter")
    assert find_kind("Yeni Bir Parça", "") is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("VOLKSWAGEN", "Volkswagen"), ("BMW", "BMW"), ("MERCEDES-BENZ", "Mercedes-Benz"), ("CITROЁN", "Citroën"),
        ("LAND ROVER", "Land Rover"), ("BLUE PRINT", "Blue Print"), ("SKF", "SKF"), ("Schaeffler LuK", "Schaeffler LuK"),
        ("X-TRAIL", "X-Trail"), ("CR-V", "CR-V"), ("TRANSIT Custom", "Transit Custom"), ("LEMFÖRDER", "Lemförder"),
    ],
)
def test_proper_name(raw, expected):
    assert proper_name(raw) == expected


def test_model_series_are_translated():
    assert (model_name("3 Serisi", "ru"), model_name("3 Serisi", "en")) == ("3 серии", "3 Series")
    assert (model_name("S-Serisi", "ru"), model_name("S-Serisi", "en")) == ("S-класса", "S-Class")


def test_only_known_numeric_specs_are_translated():
    assert translate_spec("Uzunluk [mm]", "107") == ("Длина: 107 мм", "Length: 107 mm")
    assert translate_spec("Genişlik 1 [mm]", "155,3") == ("Ширина 1: 155,3 мм", "Width 1: 155.3 mm")
    assert translate_spec("Delik sayısı", "5") == ("Число отверстий: 5", "Number of holes: 5")
    assert translate_spec("Montaj tarafı", "Ön aks") is None  # значение-слово не переводим
    assert translate_spec("Motor kodu", "AEF; AEG") is None


def _generator():
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.vector_store = None
    generator.result_applier = AIResultApplier()
    generator._get_prompt_template = lambda *_args, **_kwargs: ""
    generator.llm = SimpleNamespace(
        model="test-model",
        generate_content=Mock(side_effect=AssertionError("модель для автозапчасти не вызывается")),
        analyze_images=Mock(side_effect=AssertionError("фото автозапчасти не анализируются")),
    )
    return generator


def _part(kind="Fren Disk Balata", crumbs=("Oto Yedek Parça", "Yedek Parça", "Fren", "Fren Balatası", "Fren Disk Balata"),
          fitments=(("SEAT", "ALHAMBRA"), ("VOLKSWAGEN", "TIGUAN"), ("AUDI", "Q3")), slug="fren-disk-balata-delphi-lp2110"):
    root, _ = Category.objects.get_or_create(slug="auto-parts", defaults={"name": "Автозапчасти"})
    category, _ = Category.objects.get_or_create(slug="brake-pads", defaults={"name": "Тормозные колодки", "parent": root})
    brand, _ = Brand.objects.get_or_create(slug="delphi", defaults={"name": "DELPHI"})
    part = AutoPartProduct.objects.create(
        name=f"{kind} DELPHI LP2110", slug=slug, category=category, brand=brand, part_number="LP2110",
        price=1636.34, currency="TRY", description="FREN BALATASI ÖN VAG TIGUAN Q3 SHARAN 07-19",
        external_id=f"aloparca-{slug}",
        external_data={
            "source": "aloparca",
            "attributes": {
                "part_number": "LP2110", "part_kind_tr": kind, "aloparca_breadcrumbs": list(crumbs),
                "specs": {"Genişlik 1 [mm]": "155,3", "Montaj tarafı": "Ön aks", "Kalınlık 1 [mm]": "19,5"},
            },
        },
    )
    for number in ("5N0698151", "5N0 698 151 A"):
        AutoPartNumber.objects.create(product=part, number=number, maker="AUDI, VW", source="aloparca")
    for make, model in fitments:
        AutoPartFitment.objects.create(product=part, make=make, model=model, source="aloparca")
    part.refresh_from_db()
    return part


@pytest.mark.django_db
def test_titles_follow_the_template():
    content = run_auto_part_content(_part().base_product)["content"]

    assert content["ru"]["generated_title"] == "Тормозные колодки дисковые Delphi LP2110 для Seat, Volkswagen, Audi"
    assert content["en"]["generated_title"] == "Delphi LP2110 Disc Brake Pads for Seat, Volkswagen, Audi"
    assert content["ru"]["seo_title"] == "Тормозные колодки дисковые Delphi LP2110 — купить из Турции"
    assert len(content["ru"]["seo_title"]) <= 80 and len(content["ru"]["seo_description"]) <= 200
    assert "OEM: 5N0698151" in content["ru"]["seo_description"]
    description = content["ru"]["generated_description"]
    assert "Подходит для автомобилей Seat, Volkswagen, Audi" in description
    assert "OEM-номера: 5N0698151, 5N0 698 151 A." in description
    assert "<li>Ширина 1: 155,3 мм</li>" in description and "Montaj" not in description
    assert "LP2110" in content["ru"]["keywords"] and "5N0698151" in content["ru"]["keywords"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "fitments,tail_ru,tail_en",
    [
        ((("NISSAN", "X-TRAIL"),), " для Nissan X-Trail", " for Nissan X-Trail"),
        ((("BMW", "3 Serisi"), ("BMW", "4 Serisi")), " для BMW 3 серии, 4 серии", " for BMW 3 Series, 4 Series"),
        ((("FORD", "A"), ("FORD", "B"), ("FORD", "C"), ("FORD", "D")), " для Ford", " for Ford"),
        ((("FORD", "A"), ("OPEL", "B"), ("FIAT", "C"), ("SAAB", "D")), "", ""),
        ((), "", ""),
    ],
)
def test_fitment_tail(fitments, tail_ru, tail_en):
    titles = build_auto_part_titles(collect_auto_part_facts(_part(fitments=fitments).base_product))

    assert titles["ru"] == f"Тормозные колодки дисковые Delphi LP2110{tail_ru}"
    assert titles["en"] == f"Delphi LP2110 Disc Brake Pads{tail_en}"


@pytest.mark.django_db
def test_unknown_kind_is_an_error_not_an_invented_title():
    part = _part(kind="Yeni Bir Parça", crumbs=("Oto Yedek Parça", "Yedek Parça", "Yeni", "Yeni Bir Parça"))

    with pytest.raises(AutoPartKindUnknown, match="Yeni Bir Parça"):
        run_auto_part_content(part.base_product)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "options",
    [{"analyze_images": False, "categorize": False, "force": True}, {}],
    ids=["explicit", "queue-defaults"],
)
def test_processing_applies_russian_card_without_calling_a_model(options):
    """Вторая строка — как ставит парсер и кнопка админки: без опций, модель всё равно не вызывается."""
    part = _part()
    generator = _generator()

    log = generator.process_product(part.base_product.id, auto_apply=True, options=options)

    log.refresh_from_db()
    assert log.status == AIProcessingStatus.APPROVED, (log.error_message, log.application_report)
    assert float(log.cost_usd or 0) == 0 and not generator.llm.generate_content.called
    part.refresh_from_db()
    assert part.name == "Тормозные колодки дисковые Delphi LP2110 для Seat, Volkswagen, Audi"
    assert part.base_product.name == part.name
    assert "OEM-номера" in part.description
    english = part.translations.get(locale="en")
    assert english.name == "Delphi LP2110 Disc Brake Pads for Seat, Volkswagen, Audi"
    # Факты для повторной обработки — в атрибутах источника, от названия они не зависят.
    assert part.external_data["attributes"]["part_kind_tr"] == "Fren Disk Balata"
    again = run_auto_part_content(part.base_product)["content"]
    assert again["ru"]["generated_title"] == part.name


@pytest.mark.django_db
def test_rescrape_keeps_the_russian_card_and_updates_price():
    from apps.scrapers.base.scraper import ScrapedProduct
    from apps.scrapers.models import ScraperConfig, ScrapingSession
    from apps.scrapers.services import ScraperIntegrationService

    part = _part()
    _generator().process_product(
        part.base_product.id, auto_apply=True, options={"analyze_images": False, "categorize": False, "force": True},
    )
    config = ScraperConfig.objects.create(
        name="aloparca-ai", parser_class="aloparca", base_url="https://aloparca.com",
        default_category=Category.objects.get(slug="auto-parts"), is_multibrand=True,
    )
    session = ScrapingSession.objects.create(scraper_config=config, status="running", start_url="https://aloparca.com")
    scraped = ScrapedProduct(
        name="Fren Disk Balata DELPHI LP2110", description="FREN BALATASI ÖN VAG TIGUAN Q3 SHARAN 07-19",
        price=1700.0, currency="TRY", url="https://aloparca.com/product/delphi-lp2110-fren-balatasi",
        brand="DELPHI", external_id=part.external_id, sku="LP2110", source="aloparca",
        attributes={"aloparca_category_slugs": ["brake-pads", "brake-system", "auto-parts"], "part_kind_tr": "Fren Disk Balata"},
    )

    result = ScraperIntegrationService()._process_scraped_products(session, [scraped])

    assert result["errors"] == 0
    part.refresh_from_db()
    assert float(part.price) == 1700.0
    assert part.name == "Тормозные колодки дисковые Delphi LP2110 для Seat, Volkswagen, Audi"
    assert "OEM-номера" in part.description


@pytest.mark.django_db
def test_kind_named_like_another_section_is_not_sent_to_moderation():
    """«Компрессор кондиционера» в «Системе охлаждения»: вид из словаря, а не догадка модели."""
    root, _ = Category.objects.get_or_create(slug="auto-parts", defaults={"name": "Автозапчасти"})
    Category.objects.create(slug="air-conditioners", name="Кондиционеры")
    Category.objects.create(slug="alternators", name="Генераторы", parent=root)
    part = _part(kind="Klima Kompresörü", crumbs=("Oto Yedek Parça", "Yedek Parça", "Soğutma", "Klima Kompresörü"))

    log = _generator().process_product(
        part.base_product.id, auto_apply=True, options={"analyze_images": False, "categorize": False, "force": True},
    )

    log.refresh_from_db()
    assert log.status == AIProcessingStatus.APPROVED, log.application_report
    part.refresh_from_db()
    assert part.name.startswith("Компрессор кондиционера Delphi LP2110")
