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
        # «1910» у инвентаря — номер модели, а не артикул: и «CLS TRN» за ним остаётся.
        (
            "Everlast 1910 CLS TRN 14OZ Unisex Siyah Boks Eldiveni", "Everlast",
            "Боксёрские перчатки Everlast 1910 CLS TRN, 14 унций, черные", "Everlast 1910 CLS TRN Boxing Gloves, 14 oz, Black",
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


def test_unknown_turkish_word_leaves_title_to_the_model():
    # «Lig» — турецкое слово без турецких букв (список SPORTS_PLAIN_TURKISH_WORDS), «Kupası» — с буквой «ı».
    assert _titles("adidas Türkiye TFF 26/27 Lig Beyaz Futbol Topu", "adidas") == {"ru": "", "en": ""}
    assert _titles("adidas 2026 Fıfa Dünya Kupası Final Topu", "adidas") == {"ru": "", "en": ""}
    # Опечатка источника с турецкой «ı» — не модель.
    assert _titles("Everlast Powerlock Traınıng Gloves Siyah Boks Eldiveni", "Everlast") == {"ru": "", "en": ""}


@pytest.mark.parametrize(
    "name, brand, ru",
    [
        # Пилот 12.11.2026: «Футбольный мяч Adidas TFF», «…Force 290», «Синий мини-мяч … для футбола».
        ("adidas TFF 26/27 Beyaz Unisex Competition Futbol Topu", "adidas", "Футбольный мяч adidas TFF 26/27 Competition, белый"),
        ("adidas TFF 26/27 Beyaz Unisex Club Futbol Topu", "adidas", "Футбольный мяч adidas TFF 26/27 Club, белый"),
        ("Pro Touch Force 290 Beyaz Lite Futbol Topu", "Pro Touch", "Футбольный мяч Pro Touch Force 290 Lite, белый"),
        ("Pro Touch Force Unisex Mini Mavi Futbol Topu", "Pro Touch", "Футбольный мяч Pro Touch Force Mini, синий"),
        ("Nike Skills No3 Unisex Turuncu Mini Basketbol Topu", "Nike", "Баскетбольный мяч Nike Skills Mini, размер 3, оранжевый"),
        ("Wilson Padel Raketi Carbon Force 2 Unisex Gri Padel Raketi", "Wilson", "Ракетка для падела Wilson Carbon Force 2, серая"),
        ("Bolle Ski Helmet Atmos Pure 52-55cm Unisex Beyaz Kask", "Bolle", "Горнолыжный шлем Bolle Atmos Pure, 52–55 см, белый"),
        # Номера моделей: две разные ракетки — два названия.
        ("Pro Touch Pro 1000 Siyah Masa Tenis Raketi", "Pro Touch", "Ракетка для настольного тенниса Pro Touch 1000, черная"),
        ("Pro Touch Pro 2000 Siyah Masa Tenis Raketi", "Pro Touch", "Ракетка для настольного тенниса Pro Touch 2000, черная"),
        ("Nike All Court Dikişli No 5 Unisex Beyaz Voleybol Topu", "Nike", "Волейбольный мяч Nike All Court с прошитыми швами, размер 5, белый"),
        ("Nike Türkiye 26/27 Unisex Kırmızı Futbol Topu", "Nike", "Футбольный мяч Nike 26/27 Турция, красный"),
        # Повтор слова модели и размер в конце названия.
        (
            "Energetics Deluxe Chinning Bar Siyah Antrenman Deluxe Barfiks Çubuğu", "Energetics",
            "Турник Energetics Deluxe Chinning Bar для тренировок, черный",
        ),
        ("Pro Touch Wrist Support 100 Unisex Siyah Bilek Korumalığı Xs", "Pro Touch", "Фиксатор запястья Pro Touch Wrist Support 100, черный"),
    ],
)
def test_model_words_after_kind_are_kept(name, brand, ru):
    assert _titles(name, brand)["ru"] == ru


def test_kind_is_the_last_one_in_the_name():
    """«Grip» и «Bone» бывают словами модели и цвета: вид товара — в конце названия."""
    assert _titles("McKinley Active Grip Unisex Mavi Kayak Takımı", "McKinley")["ru"] == (
        "Горные лыжи с креплениями McKinley Active Grip, синие"
    )
    assert _titles("Nike Academy Light Bone Unisex Futbol Topu", "Nike")["ru"] == "Футбольный мяч Nike Academy Light Bone"
    assert _titles("Speedo Pace Cap Unisex Pembe Bone", "Speedo")["ru"] == "Шапочка для плавания Speedo Pace Cap, розовая"
    assert _titles("Wilson Pro Overgrip Pk Pembe Grip", "Wilson")["ru"] == "Обмотка для ракетки Wilson Pro Overgrip Pk, розовая"


def test_turkish_plain_words_are_not_taken_for_model():
    """Турецкие слова без турецких букв, которые знает словарь, моделью не становятся."""
    facts = ProductFacts(product_type="sports", brand="Energetics")
    parse_name("Energetics Unisex Siyah Masa Aleti", facts)
    assert facts.model == "" and facts.untranslated == ["Masa", "Aleti"]
    # У одежды правило не действует: латинское слово после типа — по-прежнему непереведённое.
    facts = ProductFacts(product_type="clothing", brand="Nike")
    parse_name("Nike Erkek Siyah Competition Tişört", facts)
    assert facts.untranslated == ["Competition"]


def test_same_named_mats_differ_by_thickness_from_description():
    """Два коврика «Energetics Unisex Siyah Yoga Matı»: у одного в описании толщина 10 мм."""
    product = SimpleNamespace(product_type="sports", category=None, variants=None, domain_item=None)
    data = {
        "name": "Energetics Unisex Siyah Yoga Matı", "brand": "Energetics",
        "description": "<p>Ürünün boyutları 140 cm × 60 cm, kalınlığı 10 mm olup, malzemesi NBR şeklindedir.</p>",
    }
    assert build_titles(collect_facts(product, data))["ru"] == "Коврик для йоги Energetics, толщина 10 мм, черный"
    data["description"] = "<p>Özel olarak kabartılmış yüzey, her egzersizde güvenli bir tutuş sağlar.</p>"
    assert build_titles(collect_facts(product, data))["ru"] == "Коврик для йоги Energetics, черный"
    # У товара с моделью в названии толщина из описания не берётся.
    data.update(name="Energetics PVC Free 1.0 Siyah Yoga Matı", description="<p>6 mm kalınlığındaki yapı.</p>")
    assert build_titles(collect_facts(product, data))["ru"] == "Коврик для йоги Energetics PVC Free 1.0, черный"


def test_sports_words_do_not_touch_clothing():
    """«Bone» — цвет Nike, «Mat» — матовый: у одежды это не шапочка и не коврик."""
    facts = ProductFacts(product_type="clothing")
    parse_name("Nike Sportswear Light Bone Erkek Tişört", facts)
    assert facts.kind.ru == "футболка"
    assert "bone" not in vocab.turkish_title_words("clothing") and "kask" not in vocab.turkish_title_words("clothing")
    assert "kask" in vocab.turkish_title_words("sports") and "tekmelik" in vocab.turkish_title_words("sports")
    # Английские слова, совпадающие с турецкими видами, в названии допустимы.
    assert {"bone", "snorkel", "kettlebell", "mat", "grip"}.isdisjoint(vocab.turkish_title_words("sports"))


def test_multilayer_lens_is_not_millilitres():
    """Пилот 12.11.2026: «Salomon S/view 3 Ml» стал «…, 3 мл» — у инвентаря объёма в названии нет."""
    assert _titles("Salomon S/view 3 Ml Unisex Mavi Kayak Gözlüğü", "Salomon") == {
        "ru": "Горнолыжная маска Salomon S/view 3 Ml, синяя", "en": "Salomon S/view 3 Ml Ski Goggles, Blue",
    }
    facts = ProductFacts(product_type="perfumery")
    parse_name("Loris 50 ml Erkek Parfüm", facts)
    assert facts.volume == ("50 мл", "50 ml")
    # Настоящий объём у спорттовара остаётся: бутылка, спрей.
    facts = ProductFacts(product_type="sports")
    parse_name("Nike Hyperfuel 750 ml Unisex Siyah Suluk", facts)
    assert facts.volume == ("750 мл", "750 ml")


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
def test_english_title_with_mat_and_grip_is_not_untranslated():
    """«Yoga Mat», «Racket Grip» — английские слова, а не турецкие «mat» и «grip» (2 модерации пилота)."""
    yoga = Category.objects.create(name="Коврики для йоги", slug="yoga-mats")
    brand = Brand.objects.create(name="Energetics", slug="energetics")
    product = Product.objects.create(
        name="Energetics Unisex Siyah Yoga Matı", slug="sp-yoga-mat", product_type="sports", category=yoga, brand=brand,
    )
    titles = {"ru": "Коврик для йоги Energetics, черный", "en": "Energetics Yoga Mat, Black"}
    assert SemanticValidator().validate(product, generated_titles=titles, dynamic_attributes=[]).reasons == []


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
