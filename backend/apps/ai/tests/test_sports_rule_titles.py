"""Спортивный инвентарь (Intersport, SuperStep) — названия правилами, как у обуви и одежды.

Названия источника — настоящие строки intersport.com.tr от 12.11.2026.
"""

from types import SimpleNamespace

import pytest

from apps.ai.services.rules import vocab
from apps.ai.services.rules.facts import (
    RULE_PRODUCT_TYPES,
    ProductFacts,
    clean_source_text,
    collect_facts,
    parse_name,
)
from apps.ai.services.rules.text import build_titles
from apps.ai.services.semantic_validator import SemanticValidator
from apps.catalog.models import Brand, Category, CategoryTranslation, Product


def _titles(name, brand, category=None, **attributes):
    product = SimpleNamespace(
        product_type="sports", category=SimpleNamespace(slug=category) if category else None,
        variants=None, domain_item=None,
    )
    return build_titles(collect_facts(product, {"name": name, "brand": brand, "attributes": attributes}))


def test_sports_goods_are_written_by_rules():
    assert "sports" in RULE_PRODUCT_TYPES
    assert "tableware" not in RULE_PRODUCT_TYPES  # посуда — по-прежнему моделью


@pytest.mark.parametrize(
    "name, brand, ru, en",
    [
        ("Nike Academy Unisex Beyaz Futbol Topu", "Nike", "Футбольный мяч Nike Academy, белый", "Nike Academy Football, White"),
        (
            "Jordan Ultimate 2.0 7 No Turuncu Basketbol Topu", "Jordan",
            "Баскетбольный мяч Jordan Ultimate 2.0, размер 7, оранжевый", "Jordan Ultimate 2.0 Basketball, Size 7, Orange",
        ),
        (
            "Arena Classic Silicone Unisex Beyaz Havuz Bonesi", "Arena",
            "Шапочка для плавания Arena Classic Silicone, белая", "Arena Classic Silicone Swim Cap, White",
        ),
        (
            "Speedo Hydropulse Aynalı Unisex Siyah Yüzücü Gözlüğü", "Speedo",
            "Очки для плавания Speedo Hydropulse с зеркальными линзами, черные",
            "Speedo Hydropulse Mirrored Swimming Goggles, Black",
        ),
        ("Energetics Siyah 2Kg Dambıl Seti", "Energetics", "Набор гантелей Energetics, 2 кг, черный", "Energetics Dumbbell Set, 2 kg, Black"),
        (
            "Energetics Siyah 0,5Kg Bilek Ağırlığı", "Energetics",
            "Утяжелители для запястий Energetics, 0,5 кг, черные", "Energetics Wrist Weights, 0.5 kg, Black",
        ),
        ("Energetics Unisex Gri Pilates Topu 65cm", "Energetics", "Мяч для пилатеса Energetics, 65 см, серый", "Energetics Pilates Ball, 65 cm, Gray"),
        # «1910 CLS TRN» — цифры и короткие коды за ними правила считают артикулом (как у одежды).
        (
            "Everlast 1910 CLS TRN 14OZ Unisex Siyah Boks Eldiveni", "Everlast",
            "Боксёрские перчатки Everlast, 14 унций, черные", "Everlast Boxing Gloves, 14 oz, Black",
        ),
        (
            "Oakley Mod5 Erkek Gri Kayak/Snowboard Kaskı", "Oakley",
            "Мужской горнолыжный шлем Oakley Mod5, серый", "Oakley Mod5 Men's Ski Helmet, Gray",
        ),
        (
            "McKinley Flyte Jr Revo Unisex Yeşil Kayak/Snowboard Gözlüğü", "McKinley",
            "Горнолыжная маска McKinley Flyte Jr Revo, зеленая", "McKinley Flyte Jr Revo Ski Goggles, Green",
        ),
        (
            "Nike Mercurial Lite SuperLock Unisex Lacivert Futbol Dizlik", "Nike",
            "Футбольные щитки Nike Mercurial Lite SuperLock, темно-синие", "Nike Mercurial Lite SuperLock Football Shin Guards, Navy",
        ),
        (
            "Wilson Us Open Xd Tball 3lü Sarı Tenis Topu", "Wilson",
            "Теннисные мячи Wilson Us Open Xd Tball, 3 шт., желтые", "Wilson Us Open Xd Tball Tennis Balls, 3-Pack, Yellow",
        ),
        ("McKinley Pro 5 Çocuk Lacivert Uyku Tulumu", "McKinley", "Детский спальный мешок McKinley Pro 5, темно-синий", "McKinley Pro 5 Kids' Sleeping Bag, Navy"),
        (
            "Firefly Phoenix III Erkek Siyah Buz Hokeyi Pateni", "Firefly",
            "Мужские хоккейные коньки Firefly Phoenix III, черные", "Firefly Phoenix III Men's Ice Hockey Skates, Black",
        ),
    ],
)
def test_equipment_titles(name, brand, ru, en):
    assert _titles(name, brand) == {"ru": ru, "en": en}


@pytest.mark.parametrize(
    "name, measure",
    [
        ("Head Mx Attitude Suprm 27 inç Siyah Tenis Raketi", ("27 дюймов", "27 in")),
        ("Bolle Atmos Pure 55-59cm Unisex Siyah Kask", ("55–59 см", "55–59 cm")),
        ("Energetics 6 mm TPE Mavi Yoga Matı", ("6 мм", "6 mm")),
        ("Nike All Court Dikişli No 5 Unisex Beyaz Voleybol Topu", ("размер 5", "Size 5")),
        ("Jordan Championship 7 Numara Turuncu Basketbol Topu", ("размер 7", "Size 7")),
        ("Speedo Biofuse 2.0 Unisex Siyah Gözlük", None),  # «2.0» — модель, а не размер
    ],
)
def test_weight_length_and_ball_size_come_from_name(name, measure):
    facts = ProductFacts(product_type="sports")
    parse_name(name, facts)
    assert facts.measure == measure


def test_measures_are_parsed_only_for_sports():
    facts = ProductFacts(product_type="clothing")
    parse_name("Nike Pro 7 No Erkek Siyah Tayt", facts)
    assert facts.measure is None


def test_unisex_is_not_written_for_equipment_but_kids_are():
    assert _titles("Speedo Jet Unisex Mavi Yüzücü Gözlüğü", "Speedo", gender="unisex")["ru"] == "Очки для плавания Speedo Jet, синие"
    assert _titles("Speedo Jet Çocuk Mavi Yüzücü Gözlüğü", "Speedo")["ru"] == "Детские очки для плавания Speedo Jet, синие"


def test_generic_word_takes_kind_from_section():
    """«Kask» — просто шлем; в «Шлемах» зимних видов — горнолыжный. «Gözlük» в очках для плавания."""
    assert _titles("Bolle Might Visor Unisex Siyah Kask", "Bolle")["ru"] == "Шлем Bolle Might Visor, черный"
    assert _titles("Bolle Might Visor Unisex Siyah Kask", "Bolle", "winter-helmets")["ru"] == "Горнолыжный шлем Bolle Might Visor, черный"
    assert _titles("Speedo Biofuse 2.0 Unisex Siyah Gözlük", "Speedo", "swimming-goggles")["ru"] == (
        "Очки для плавания Speedo Biofuse 2.0, черные"
    )
    # Вид в названии не назван вовсе («… Spor Aksesuarları» у щитков) — тоже по разделу.
    assert _titles("Nike Mercurial Lite Unisex Yeşil Spor Aksesuarları", "Nike", "shin-guards")["ru"] == (
        "Щитки Nike Mercurial Lite, зеленые"
    )


def test_unknown_word_leaves_title_to_the_model():
    assert _titles("Nike All Court Dikişli Unisex Beyaz Voleybol Topu", "Nike") == {"ru": "", "en": ""}


def test_sports_words_do_not_touch_clothing():
    """«Bone» — цвет Nike, «Mat» — матовый: у одежды это не шапочка и не коврик."""
    facts = ProductFacts(product_type="clothing")
    parse_name("Nike Sportswear Light Bone Erkek Tişört", facts)
    assert facts.kind.ru == "футболка"
    assert "bone" not in vocab.turkish_title_words("clothing") and "kask" not in vocab.turkish_title_words("clothing")
    assert "kask" in vocab.turkish_title_words("sports") and "tekmelik" in vocab.turkish_title_words("sports")
    # Английские слова, совпадающие с турецкими видами, в названии допустимы.
    assert {"bone", "snorkel", "kettlebell"}.isdisjoint(vocab.turkish_title_words("sports"))


def test_intersport_text_is_cleaned_like_superstep():
    raw = "<p>Mikasa voleybol topu.</p><p>Kombin Önerileri Şort ile kombinleyin.</p><p><strong>Teknik Özellikler</strong><li>Dayanıklı</li>"
    assert clean_source_text(raw, "intersport") == clean_source_text(raw, "superstep")
    assert "Kombin" in clean_source_text(raw, "lcw") and "kombinleyin" not in clean_source_text(raw, "intersport")


# --- проверка смысла: вид инвентаря и чужие разделы ---------------------------------


def _reasons(name, title, category_slug, category_name, parent=None, locale="ru", preloaded=False):
    sports, _ = Category.objects.get_or_create(slug="sports", defaults={"name": "Спорттовары"})
    accessories, _ = Category.objects.get_or_create(slug="accessories", defaults={"name": "Аксессуары"})
    Category.objects.get_or_create(slug="acc-gloves", defaults={"name": "Перчатки", "parent": accessories})
    Category.objects.get_or_create(slug="eyewear", defaults={"name": "Очки", "parent": accessories})
    Category.objects.get_or_create(
        slug="sunglasses", defaults={"name": "Солнцезащитные очки", "parent": accessories},
    )
    # «Ball» — английское название раздела шариковых дезодорантов (как на проде).
    ball_deodorants, _ = Category.objects.get_or_create(slug="deodorant-ball", defaults={"name": "Шариковые"})
    CategoryTranslation.objects.get_or_create(category=ball_deodorants, locale="en", defaults={"name": "Ball"})
    category, _ = Category.objects.get_or_create(
        slug=category_slug, defaults={"name": category_name, "parent": parent or sports},
    )
    brand, _ = Brand.objects.get_or_create(name="Arena", defaults={"slug": "arena"})
    product = Product.objects.create(
        name=name, slug=f"sp-{abs(hash(name))}", product_type="sports", category=category, brand=brand,
    )
    validator = SemanticValidator.with_preloaded_categories() if preloaded else SemanticValidator()
    return validator.validate(product, generated_titles={locale: title}, dynamic_attributes=[]).reasons


@pytest.mark.django_db
@pytest.mark.parametrize(
    "name, title, slug, section",
    [
        # «для» отрезает вид до «очки» — раздел «Очки» аксессуаров тут ни при чём.
        ("Arena Spider Unisex Mavi Yüzücü Gözlüğü", "Очки для плавания Arena Spider, синие", "swimming-goggles", "Очки для плавания"),
        ("adidas Predator Pro Unisex Yeşil Kaleci Eldiveni", "Вратарские перчатки adidas Predator Pro, зеленые", "football", "Футбол"),
        ("Energetics MFG370 Antrenman Eldiveni", "Перчатки для фитнеса Energetics MFG370, черные", "fitness-gloves", "Перчатки для фитнеса"),
    ],
)
def test_equipment_kind_is_not_mistaken_for_accessory_section(name, title, slug, section):
    assert "title_category_mismatch" not in _reasons(name, title, slug, section)


@pytest.mark.django_db
def test_plain_accessory_title_in_sports_section_is_still_a_mismatch():
    """Просто «Перчатки» в «Футболе» — не инвентарь из словаря: проверка остаётся."""
    assert "title_category_mismatch" in _reasons(
        "Nike Pacer Unisex Siyah Eldiven", "Перчатки Nike Pacer, черные", "football", "Футбол",
    )


# Верные карточки SuperStep (партия 9, 12.11.2026) ушли на модерацию из-за этой проверки.
@pytest.fixture
def sports_tree():
    """Разделы как на проде: «Плавание → Очки для плавания», «Баскетбол → Баскетбольные мячи»."""
    sports, _ = Category.objects.get_or_create(slug="sports", defaults={"name": "Спорттовары"})
    for parent_slug, parent_name, parent_en, slug, name, en in (
        ("swimming", "Плавание", "Swimming", "swimming-goggles", "Очки для плавания", "Swimming goggles"),
        ("basketball", "Баскетбол", "Basketball", "basketball-balls", "Баскетбольные мячи", "Basketball balls"),
    ):
        parent = Category.objects.create(slug=parent_slug, name=parent_name, parent=sports)
        CategoryTranslation.objects.create(category=parent, locale="en", name=parent_en)
        child = Category.objects.create(slug=slug, name=name, parent=parent)
        CategoryTranslation.objects.create(category=child, locale="en", name=en)


_SWIMMING_GOGGLES = ("Speedo Jet Çocuk Mavi Yüzücü Gözlüğü", "swimming-goggles", "Очки для плавания")
_SWIMMING = ("Sunnylife Çocuk Yüzücü Gözlüğü", "swimming", "Плавание")
_BASKETBALL_BALLS = ("Jordan Championship 7 No Turuncu Basketbol Topu", "basketball-balls", "Баскетбольные мячи")


@pytest.mark.django_db
@pytest.mark.parametrize("preloaded", [False, True])
@pytest.mark.parametrize(
    "title, locale, section",
    [
        ("Детские очки для плавания Speedo Jet, синие", "ru", _SWIMMING_GOGGLES),
        ("Детские плавательные очки Sunnylife", "ru", _SWIMMING_GOGGLES),
        ("Детские плавательные очки Sunnylife", "ru", _SWIMMING),
        ("Jordan Championship 7 Basketball Ball", "en", _BASKETBALL_BALLS),
    ],
)
def test_superstep_batch9_sports_titles_are_not_mismatch(sports_tree, title, locale, section, preloaded):
    name, slug, section_name = section
    reasons = _reasons(name, title, slug, section_name, locale=locale, preloaded=preloaded)
    assert "title_category_mismatch" not in reasons


@pytest.mark.django_db
@pytest.mark.parametrize("preloaded", [False, True])
@pytest.mark.parametrize(
    "title, section",
    [
        ("Солнцезащитные очки Speedo Jet, синие", _SWIMMING_GOGGLES),
        ("Детские солнцезащитные очки Sunnylife", _SWIMMING),
        ("Очки Sunnylife, синие", _SWIMMING),
    ],
)
def test_sunglasses_in_swimming_section_are_still_a_mismatch(sports_tree, title, section, preloaded):
    name, slug, section_name = section
    assert "title_category_mismatch" in _reasons(name, title, slug, section_name, preloaded=preloaded)
