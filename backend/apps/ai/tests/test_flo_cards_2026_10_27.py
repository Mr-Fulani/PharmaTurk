"""Партия 500 карточек FLO через Claude 27.10.2026: брак и ложные причины модерации.

Примеры — товары прода (pid в комментарии).
"""

from types import SimpleNamespace

import pytest

from apps.ai.services.rules.facts import ProductFacts, parse_name
from apps.ai.services.rules.pipeline import _checked_llm_title
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
        # Принт без словаря уходил в LLM: «с круглым вырезом в вертикальный рубчик» у поло.
        (
            20132, "Erkek Polo Yaka Çapa Desenli %100 Pamuk Tişört", "clothing", "",
            "Мужская футболка с отложным воротником из хлопка", "Men's Polo Collar Cotton T-Shirt",
        ),
        (
            19001, "Only & Sons Erkek T Shirt 22022532 AÇIK HAKİ", "clothing", "Only & Sons",
            "Мужская футболка Only & Sons, светло-хаки", "Only & Sons Men's T-Shirt, Light khaki",
        ),
        # Бренд каталога «Only&Sons» без пробелов — не дважды («футболка Only&Sons Only & Sons»):
        # бренд в названии с другими пробелами и точками вырезается, пишется бренд каталога.
        (
            19001, "Only & Sons Erkek T Shirt 22022532 AÇIK HAKİ", "clothing", "Only&Sons",
            "Мужская футболка Only&Sons, светло-хаки", "Only&Sons Men's T-Shirt, Light khaki",
        ),
        # «Us. Polo Assn.» при бренде «U.S. Polo Assn.»: «Polo» из бренда — не тип «поло».
        (
            20802, "Us. Polo Assn. Erkek Tişört", "clothing", "U.S. Polo Assn.",
            "Мужская футболка U.S. Polo Assn.", "U.S. Polo Assn. Men's T-Shirt",
        ),
        # «® |» и «Taba-Erkek» (цвет и пол через дефис) — правила не собирали название.
        (
            11241, "® | PC-5112-3892 Taba-Erkek Sandalet", "shoes", "Pierre Cardin",
            "Мужские сандалии Pierre Cardin, рыжие", "Pierre Cardin Men's Sandals, Tan",
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


@pytest.mark.parametrize(
    "pid, title, locale",
    [
        (11203, "Мужские сандалии Siyah Lastikli из натуральной кожи", "ru"),
        (11358, "Мужские сандалии Kum Nubuk", "ru"),
        (11358, "Kum Nubuck Genuine Leather Men's Sandals 1405", "en"),
        (11164, "Мужские сандалии Pierre Cardin Taba", "ru"),
        # Имя магазина из промпта вместо бренда.
        (20323, "Мужская спортивная футболка Mudaroba в полоску из полиэстера", "ru"),
    ],
)
def test_llm_title_with_turkish_vocab_word_is_rejected(pid, title, locale):
    assert _checked_llm_title(title, ProductFacts(product_type="shoes"), locale) == "", pid


@pytest.mark.parametrize(
    "title, locale, brand",
    [
        ("Мужская футболка Buratti с воротником-поло", "ru", ""),
        ("Men's Basic Crew Neck T-Shirt 5-Pack, Cotton", "en", ""),
        ("Jack & Jones Men's Logo Polo T-Shirt", "en", "Jack & Jones"),
        ("Мужская футболка Mavi с принтом", "ru", "Mavi"),  # бренд, а не цвет
    ],
)
def test_llm_title_with_english_words_is_kept(title, locale, brand):
    facts = ProductFacts(product_type="clothing", brand=brand)

    assert _checked_llm_title(title, facts, locale) == title


@pytest.mark.django_db
def test_apparel_title_with_turkish_vocab_word_goes_to_moderation():
    # 11226: правилам не из чего собрать название, LLM-вариант «Crocband Krem» уходил на сайт.
    shoes, _ = Category.objects.update_or_create(slug="shoes", defaults={"name": "Обувь", "is_active": True})
    sandals, _ = Category.objects.update_or_create(
        slug="sandals", defaults={"name": "Сандалии", "parent": shoes, "is_active": True}
    )
    crocs = Brand.objects.create(name="Crocs", slug="crocs")
    mavi = Brand.objects.create(name="Mavi", slug="mavi")

    def reasons(name, ru, brand):
        product = Product.objects.create(
            name=name, slug=f"krem-{brand.pk}", product_type="shoes", category=sandals, brand=brand
        )
        return SemanticValidator().validate(product, generated_titles={"ru": ru}, dynamic_attributes=[]).reasons

    assert "title_untranslated" in reasons("Crocband Krem 11016", "Мужские шлёпанцы Crocs Crocband Krem", crocs)
    assert "title_untranslated" not in reasons("Mavi Erkek Sandalet", "Мужские сандалии Mavi", mavi)


@pytest.mark.django_db
def test_dotted_capital_i_brand_keeps_identity():
    # 10663, 10918 и ещё 3: «İnci» в названии против «INCI» источника — title_identity_lost.
    shoes, _ = Category.objects.update_or_create(slug="shoes", defaults={"name": "Обувь", "is_active": True})
    sneakers, _ = Category.objects.update_or_create(
        slug="sneakers", defaults={"name": "Кроссовки", "parent": shoes, "is_active": True}
    )
    brand = Brand.objects.create(name="İnci", slug="inci")
    product = Product.objects.create(
        name="INCI KARVEN 6FX Beyaz Erkek Spor Ayakkabı", slug="inci-karven", product_type="shoes",
        category=sneakers, brand=brand,
    )
    reasons = SemanticValidator().validate(
        product,
        generated_titles={"ru": "Мужские кроссовки İnci KARVEN 6FX, белые", "en": "İnci KARVEN 6FX Men's Sneakers, White"},
        dynamic_attributes=[],
    ).reasons

    assert "title_identity_lost" not in reasons
