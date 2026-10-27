"""Партия 500 карточек FLO через Claude 27.10.2026: брак и ложные причины модерации.

Примеры — товары прода (pid в комментарии).
"""

from types import SimpleNamespace

import pytest

from apps.ai.services.rules.facts import ProductFacts, parse_name
from apps.ai.services.rules.text import build_titles
from apps.ai.services.semantic_validator import SemanticValidator
from apps.ai.services.size_inventory import extract_sizes_from_input, variant_size_identities
from apps.catalog.models import Brand, Category, Product


def _titles(name, product_type, brand=""):
    facts = ProductFacts(product_type=product_type, brand=brand)
    parse_name(name, facts)
    return build_titles(facts)


@pytest.mark.parametrize(
    "pid, name, product_type, brand, ru, en",
    [
        # Цвет принимали за модель: «Мужская футболка Discovery Expedition Hardal».
        (
            20379, "Hardal Erkek T-Shirt D6SU-TST3102", "clothing", "Discovery Expedition",
            "Мужская футболка Discovery Expedition, горчичная", "Discovery Expedition Men's T-Shirt, Mustard",
        ),
        (
            20986, "D6SM-TST3804 Koyu Mint Bisiklet Yaka Rahat Düz Erkek T-Shirt", "clothing", "Discovery Expedition",
            "Мужская футболка Discovery Expedition с круглым вырезом, темно-мятная",
            "Discovery Expedition Men's Crew Neck T-Shirt, Dark mint",
        ),
        (
            10699, "CAMBRIA 6FX Saks Erkek Sneaker", "shoes", "Kinetix",
            "Мужские кроссовки Kinetix CAMBRIA 6FX, голубые", "Kinetix CAMBRIA 6FX Men's Sneakers, Saxe blue",
        ),
        # «Dr. Tavsiyeli» (рекомендовано врачом) оставалось в названии по-турецки.
        (
            11311, "80-954 Dr. Tavsiyeli Ortapedik Erkek Sandalet", "shoes", "ARYAN",
            "Мужские сандалии ARYAN с ортопедической стелькой", "ARYAN Men's Orthopedic Sandals",
        ),
        (
            11359, "Aryan D.r Tavsiyeli Ortapedik Erkek Sandalet", "shoes", "ARYAN",
            "Мужские сандалии ARYAN с ортопедической стелькой", "ARYAN Men's Orthopedic Sandals",
        ),
        (
            11329, "Ayakkabiburada 033 Topuk Jelli Hakiki Deri Erkek Sandalet Ayakkabı", "shoes", "",
            "Мужские сандалии Ayakkabiburada 033 из натуральной кожи",
            "Ayakkabiburada 033 Men's Genuine Leather Sandals",
        ),
    ],
)
def test_flo_titles(pid, name, product_type, brand, ru, en):
    assert _titles(name, product_type, brand) == {"ru": ru, "en": en}, pid


def test_bebek_is_kids_audience():
    # 11235, 11172: детские сандалии «Bebek» получали «Мужские сандалии Renkli/Petrol».
    facts = ProductFacts(product_type="shoes")
    parse_name("Petrol Yeşili Cırtlı Işıklı Hafif Bebek Sandalet Sage B", facts)

    assert facts.audience == ("детский", "Kids'")
    assert facts.color is not None and facts.color.en == "Petrol green"


def test_sizes_ignore_escaped_html_markup():
    # 18848, 19366, 11244: «size» из «font-size» и числа из «data-start=&quot;67&quot;»,
    # «line-height: 107%», «%100 Pamuk» становились размерами → ambiguous_variant_sizes.
    description = (
        "&lt;div&gt;&lt;span style=&quot;font-size: large;&quot;&gt;Tekstil etiketleri&lt;/span&gt;&lt;/div&gt; "
        "&lt;div&gt;&lt;span style=&quot;font-size: large;&quot;&gt;Kabuk %100 Pamuk&lt;/span&gt;&lt;/div&gt;"
        "&lt;div&gt;&lt;strong data-start=&quot;67&quot; data-end=&quot;85&quot;&gt;Tasar&amp;#305;m &amp;amp; Renk"
        "&lt;/strong&gt;&lt;/div&gt;&lt;span style=&quot;line-height: 107%; color: rgb(24, 24, 24);&quot;&gt;"
        "Crush Clog&lt;/span&gt;"
    )
    rows = extract_sizes_from_input(
        {"raw_description": description, "attributes": {"sizes": ["M", "S", "L"]}}, "clothing"
    )

    assert [row["size"] for row in rows] == ["M", "S", "L"]


def test_sizes_in_escaped_html_are_still_found():
    rows = extract_sizes_from_input({"description": "&lt;p&gt;Bedenler: S, M, L&lt;/p&gt;"}, "clothing")

    assert [row["size"] for row in rows] == ["S", "M", "L"]


def test_us_eu_variant_sizes_match_eu_size():
    # 11117: у вариантов «10(43)», «11(44)», из текста — «43», «44».
    variants = SimpleNamespace(values_list=lambda *args, **kwargs: ["10(43)", "11(44)", "40", None])

    assert variant_size_identities(SimpleNamespace(variants=variants)) >= {"43", "44", "40", "10(43)"}


@pytest.mark.django_db
def test_brand_word_is_not_category_conflict():
    # 19905 и ещё 7 футболок Tommy Jeans: «Jeans» из бренда — не раздел «Джинсы».
    clothing, _ = Category.objects.update_or_create(slug="clothing", defaults={"name": "Одежда", "is_active": True})
    tshirts, _ = Category.objects.update_or_create(
        slug="t-shirts", defaults={"name": "Футболки", "parent": clothing, "is_active": True}
    )
    jeans, _ = Category.objects.update_or_create(
        slug="jeans", defaults={"name": "Джинсы", "parent": clothing, "is_active": True}
    )
    for category, en in ((clothing, "Clothing"), (tshirts, "T-Shirts"), (jeans, "Jeans")):
        category.translations.update_or_create(locale="en", defaults={"name": en})
    brand = Brand.objects.create(name="Tommy Jeans", slug="tommy-jeans")

    def reasons(brand):
        product = Product.objects.create(
            name="Erkek T Shirt DM0DM23183 YBH", slug=f"tj-{brand and brand.pk}", product_type="clothing",
            category=tshirts, brand=brand,
        )
        return SemanticValidator().validate(
            product,
            generated_titles={
                "ru": "Мужская футболка Tommy Jeans",
                "en": "Tommy Jeans Men's Long Sleeve Striped Crew Neck T-Shirt",
            },
            dynamic_attributes=[],
        ).reasons

    assert "title_category_mismatch" not in reasons(brand)
    # Без бренда «Jeans» в названии — по-прежнему конфликт с «Джинсами».
    assert "title_category_mismatch" in reasons(None)
