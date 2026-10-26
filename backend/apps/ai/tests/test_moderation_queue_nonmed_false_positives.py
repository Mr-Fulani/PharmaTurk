"""Ложные причины модерации не медицинских товаров: разбор очереди 27.10.2026.

Примеры — логи прода (pid товара в комментарии), которые ждали модерации с верными
названиями. Рядом — настоящие ошибки из той же очереди: они должны остаться.
"""

from types import SimpleNamespace

import pytest

from apps.ai.services.rules.facts import collect_facts
from apps.ai.services.rules.text import build_titles
from apps.ai.services.semantic_validator import SemanticValidator
from apps.ai.services.size_inventory import extract_sizes_from_input
from apps.catalog.models import Category, Product

pytestmark = pytest.mark.django_db


def _category(name, slug, parent=None, en=None):
    category, _ = Category.objects.update_or_create(
        slug=slug, defaults={"name": name, "parent": parent, "is_active": True}
    )
    if en:
        category.translations.update_or_create(locale="en", defaults={"name": en})
    return category


@pytest.fixture
def catalog():
    """Фрагмент настоящего дерева (apps/catalog/constants.py) с разделами из причин очереди."""
    furniture = _category("Мебель", "furniture", en="Furniture")
    bedroom = _category("Спальня", "bedroom", furniture, "Bedroom")
    living = _category("Гостиная", "living-room", furniture, "Living Room")
    kids = _category("Детская мебель", "kids-furniture", furniture, "Kids Furniture")
    storage = _category("Хранение", "storage-furniture", furniture, "Storage")
    for name, slug, parent, en in (
        ("Кровати", "beds", bedroom, "Beds"),
        ("Основания кроватей", "bed-bases", bedroom, "Bed Bases"),
        ("Кушетки", "day-beds", bedroom, "Day Beds"),
        ("Матрасы", "mattresses", bedroom, "Mattresses"),
        ("Комоды", "dressers", bedroom, "Dressers"),
        ("Шкафы-купе и гардеробы", "wardrobes", bedroom, "Wardrobes"),
        ("Диваны", "sofas", living, "Sofas"),
        ("Диваны-кровати", "sofa-beds", living, "Sofa Beds"),
        ("Кресла", "armchairs", living, "Armchairs"),
        ("Двухъярусные кровати", "bunk-beds", kids, "Bunk Beds"),
        ("Детские шкафы", "kids-wardrobes", kids, "Kids Wardrobes"),
        ("Детские комоды", "kids-dressers", kids, "Kids Dressers"),
        ("Шкафы", "storage-cabinets", storage, "Cabinets"),
        ("Полки", "shelves", storage, "Shelves"),
    ):
        _category(name, slug, parent, en)
    auto = _category("Автозапчасти", "auto-parts", en="Auto Parts")
    _category("Пружины", "springs", auto, "Springs")
    _category("Двери", "doors", auto, "Doors")
    medical = _category("Медтехника", "medical-equipment", en="Medical Equipment")
    _category("Эластичные", "elastic-bandages", medical, "Elastic")
    _category("Ортопедические", "orthopedic-insoles", medical, "Orthopedic")
    _category("Обувь", "shoes", en="Shoes")
    _category("Спорттовары", "sports", en="Sports Goods")
    _category("Украшения", "jewelry", en="Jewelry")
    incense = _category("Благовония", "incense", en="Incense")
    _category("Уд (агаровое дерево)", "oud", incense, "Oud")
    _category("Парфюмерия", "perfumery", en="Perfumery")
    headwear = _category("Головные уборы", "headwear", en="Headwear")
    _category("Из искусственного меха", "hw-faux-fur-hats", headwear, "Faux Fur")
    clothing = _category("Одежда", "clothing", en="Clothing")
    _category("Брюки", "pants", clothing, "Pants")
    _category("Джинсы", "jeans", clothing, "Jeans")
    _category("Шорты", "shorts", clothing, "Shorts")
    islamic = _category("Исламская одежда", "islamic-clothing", en="Islamic Clothing")
    _category("Буркини", "burkini", islamic, "Burkinis")
    underwear = _category("Нижнее бельё", "underwear", en="Underwear")
    women = _category("Женское нижнее бельё", "uw-womens-underwear", underwear, "Women's Underwear")
    _category("Трусы", "uw-panties", women, "Panties")
    men = _category("Мужское нижнее бельё", "uw-mens-underwear", underwear, "Men's Underwear")
    _category("Трусы-боксеры", "uw-boxers", men, "Boxers")
    children = _category("Детское нижнее бельё", "uw-children-underwear", underwear, "Children's Underwear")
    _category("Для девочек", "uw-girls-underwear", children, "Girls")
    accessories = _category("Аксессуары", "accessories", en="Accessories")
    _category("Ремни", "belts", accessories, "Belts")
    tableware = _category("Посуда", "tableware", en="Tableware")
    _category("Хранение", "storage", tableware, "Storage")
    return {category.slug: category for category in Category.objects.all()}


def _reasons(catalog, slug, name, ru, en, product_type):
    product = Product.objects.create(
        name=name, slug=f"nm-{abs(hash((slug, name, ru)))}", product_type=product_type,
        category=catalog[slug],
    )
    return SemanticValidator().validate(
        product, generated_titles={"ru": ru, "en": en}, dynamic_attributes=[]
    ).reasons


@pytest.mark.parametrize(
    "pid, slug, name, ru, en",
    [
        # Название раздела во множественном числе, а товар — в единственном.
        (13822, "bed-bases", "LURÖY", "Реечное дно кровати IKEA LURÖY, береза", "IKEA LURÖY Slatted Bed Base, Birch"),
        (14015, "bunk-beds", "SMÅSTAD", "Двухъярусная кровать IKEA SMÅSTAD, белая", "IKEA SMÅSTAD Bunk Bed, White"),
        (
            14363, "kids-dressers", "PLATSA/SMÅSTAD", "Детский комод IKEA PLATSA/SMÅSTAD белый",
            "IKEA PLATSA/SMÅSTAD Children's Chest of Drawers White",
        ),
        # Гостевая и выдвижная кровати IKEA лежат в «Кушетках».
        (13710, "day-beds", "NORRUDDEN", "Гостевая кровать IKEA NORRUDDEN чёрная", "IKEA NORRUDDEN Black Guest Bed"),
        (13732, "day-beds", "VIHALS", "Выдвижная кровать под диван IKEA VIHALS", "IKEA VIHALS Under-Sofa Bed"),
        # Подраздел своей линии в корне «Мебель» — не конфликт.
        (
            15453, "furniture", "PLATSA/SMÅSTAD", "Детский гардероб IKEA PLATSA/SMÅSTAD белый с серым",
            "IKEA PLATSA/SMÅSTAD Children's Wardrobe White Grey",
        ),
        # Слово чужой категории после « с / with / для / из » — не тип товара.
        (
            14392, "wardrobes", "KOMPLEMENT", "Выдвижной органайзер для полки IKEA KOMPLEMENT",
            "IKEA KOMPLEMENT Pull-out Shelf Organiser",
        ),
        (
            13508, "sofas", "SALTSJÖBADEN", "Двухместный диван SALTSJÖBADEN IKEA с пружинным блоком",
            "IKEA SALTSJÖBADEN 2-Seat Sofa with Pocket Springs",
        ),
        (
            13428, "storage-cabinets", "VIHALS", "Комбинация для хранения IKEA VIHALS, белый/стекло",
            "IKEA VIHALS Storage Combination in White with Glass Doors",
        ),
    ],
)
def test_furniture_titles_from_the_queue_pass(catalog, pid, slug, name, ru, en):
    assert _reasons(catalog, slug, name, ru, en, "furniture") == [], pid


@pytest.mark.parametrize(
    "pid, slug, product_type, name, ru, en",
    [
        (
            11256, "uw-mens-underwear", "underwear", "Тройной набор боксеров", "Тройной набор боксеров Zara",
            "Zara Men's Three-Pack Boxers with Elastic Waistband",
        ),
        # Аудитория, подкатегория стелек и подкатегория шапок — не тип товара.
        (
            15372, "burkini", "islamic_clothing", "Буркини для девочек-подростков Adasea",
            "Буркини для девочек-подростков с тропическим принтом Adasea", "Adasea Burkini for Teen Girls with Tropical Print",
        ),
        (
            11141, "shoes", "shoes", "Liger Unisex Ortopedik Terlik",
            "Унисекс шлепанцы Liger ортопедические на EVA-подошве синие-красные", "Liger Unisex Orthopedic Slippers",
        ),
        (
            26177, "clothing", "clothing", "Mumlu görünümlü bomber ceket",
            "Женский бомбер Pull&Bear с воротником из искусственного меха", "Pull&Bear Women's Jacket",
        ),
        # Корни «Спорттовары» и «Украшения» — не тип товара.
        (
            10374, "belts", "accessories", "Спортивный кожаный ремень LC Waikiki",
            "Спортивный кожаный ремень LC Waikiki", "Men's Navy Genuine Leather Sports Belt LC Waikiki",
        ),
        (
            26165, "storage", "tableware", "Top Model Renksiz Sesli Ve Kilitli Mücevher Kutusu 413578",
            "Шкатулка для украшений TOP Model со звуком и замком", "TOP Model Music Jewelry Box with Lock",
        ),
        # «OUD» — название аромата из источника, а не категория благовоний.
        (
            10497, "perfumery", "perfumery", "OUD VIBRANT LEATHER EDP 100 ML (3,4 FL.OZ)",
            "Мужская парфюмерная вода Zara OUD VIBRANT LEATHER, 100 мл",
            "Zara OUD VIBRANT LEATHER Men's Eau de Parfum 100 ml",
        ),
        # «Трусы-боксеры» — подкатегория своей линии, а не женские «Трусы».
        (
            11254, "uw-mens-underwear", "underwear", "Мужские боксеры SOFT BOXER 3'ЛЮ ПАКЕТ",
            "Мужские трусы-боксеры Zara SOFT BOXER, 3 шт в упаковке", "Zara SOFT BOXER Men's Boxers, Pack of 3",
        ),
    ],
)
def test_nonmedical_titles_from_the_queue_pass(catalog, pid, slug, product_type, name, ru, en):
    assert _reasons(catalog, slug, name, ru, en, product_type) == [], pid


@pytest.mark.parametrize(
    "pid, slug, product_type, name, ru, en",
    [
        # Мужские бриджи для плавания в «Буркини», брюки в «Джинсах» — настоящие ошибки категории.
        (
            15390, "burkini", "islamic_clothing", "Новая расцветка мужских бридж для плавания",
            "Мужские бриджи Tasnim для плавания", "Tasnim Men's Swim Bridge Pants",
        ),
        (7022, "jeans", "clothing", "ZİNCİRLİ BAGGY FIT PANTOLON", "Мужские брюки Zara BAGGY", "Zara BAGGY Men's Trousers"),
        # Точный тип чужого раздела по-прежнему конфликт.
        (14015, "wardrobes", "furniture", "SMÅSTAD", "Двухъярусная кровать IKEA SMÅSTAD, белая", "IKEA SMÅSTAD Bunk Bed, White"),
        (13822, "beds", "furniture", "LURÖY", "Реечное дно кровати IKEA LURÖY, береза", "IKEA LURÖY Slatted Bed Base, Birch"),
        (14363, "wardrobes", "furniture", "PLATSA/SMÅSTAD", "Детский комод IKEA PLATSA/SMÅSTAD", "IKEA PLATSA/SMÅSTAD Chest of Drawers"),
    ],
)
def test_real_category_errors_from_the_queue_stay(catalog, pid, slug, product_type, name, ru, en):
    assert "title_category_mismatch" in _reasons(catalog, slug, name, ru, en, product_type), pid


@pytest.mark.parametrize(
    "pid, slug, product_type, name, ru",
    [
        # Диакритика: «VARKUMLA» в источнике и «VÅRKUMLA» в названии — одна модель.
        (9429, "sofa-beds", "furniture", "VARKUMLA", "Диван-кровать IKEA VÅRKUMLA синий"),
        (26188, "furniture", "furniture", "UTSADD", "Лежанка для домашних животных IKEA UTSÅDD светло-серая"),
        # Набор флаконов «2X100», «3X30ML» — объём, а не модель.
        (
            7023, "perfumery", "perfumery", "(SHAMANILLA) + (LEATHER FEVER) EDP 2X100 ML (3.38 FL. OZ)",
            "Мужская парфюмерная вода Zara (SHAMANILLA) + (LEATHER FEVER), 2 × 100 мл",
        ),
        (
            10547, "perfumery", "perfumery", "TOBACCO COLLECTION DISCOVERY SET EDP 3X30ML 1.01 FL. OZ)",
            "Мужская парфюмерная вода Zara TOBACCO COLLECTION DISCOVERY SET, 3 × 30 мл",
        ),
        # «PAKET», «BOMBER» — общие слова, «Beyaz/lacivert» — цвета, «408048.M5FX» — артикул.
        (11264, "uw-mens-underwear", "underwear", "Боксёры SOFT 3'LÜ PAKET", "Мужские боксёры Zara SOFT, 3 шт. в упаковке"),
        (26175, "clothing", "clothing", "KARELİ BOMBER CEKET", "Женский бомбер Zara в клетку"),
        (
            10481, "shoes", "shoes", "Unisex Sneaker Spor Ayakkabı 26y Ml408 Beyaz/lacivert - Белый",
            "Кроссовки унисекс New Balance 26y Ml408, белые",
        ),
        (11122, "shoes", "shoes", "408048.M5FX Gri Erkek Sandalet", "Мужские сандалии"),
    ],
)
def test_identity_false_positives_from_the_queue_pass(catalog, pid, slug, product_type, name, ru):
    assert "title_identity_lost" not in _reasons(catalog, slug, name, ru, "", product_type), pid


def test_lost_model_from_the_queue_is_still_caught(catalog):
    # 10550: правила срезали «GANGNAM-GU» — настоящая потеря модели.
    reasons = _reasons(
        catalog, "perfumery", "SEOUL 532-8 SINSA DONG GANGNAM-GU EDT 100 ML (3.04 FL. OZ)",
        "Мужская туалетная вода Zara SEOUL SINSA DONG, 100 мл", "", "perfumery",
    )
    assert "title_identity_lost" in reasons
    assert "title_identity_lost" in _reasons(
        catalog, "furniture", "UTSADD", "Лежанка для домашних животных IKEA", "", "furniture"
    )


def test_ikea_recliner_is_an_armchair_not_a_chair_bed(catalog):
    # 13479: «yatar koltuk» — реклайнер; «Кресло-кровать» конфликтовало с «Кроватями».
    product = SimpleNamespace(product_type="furniture", category=catalog["armchairs"], domain_item=None)
    facts = collect_facts(
        product, {"name": "EKOLSUND", "brand": "IKEA", "attributes": {"furniture_type": "yatar koltuk"}}
    )
    titles = build_titles(facts)

    assert titles == {"ru": "Кресло-реклайнер IKEA EKOLSUND", "en": "IKEA EKOLSUND Recliner Armchair"}
    assert _reasons(catalog, "armchairs", "EKOLSUND", titles["ru"], titles["en"], "furniture") == []


@pytest.mark.parametrize(
    "pid, product_type, description",
    [
        (
            18737, "clothing",
            "Kısa kollu ve düğme kapamalıdır. Manken Bilgisi Uzunluk 188 cm Göğüs 99 cm Bel 76 cm "
            "Basen 96 cm Manken M beden ürün giyiyor. | Ürün İçeriği ve Özellikleri",
        ),
        (
            20468, "clothing",
            "Model : Büyük Beden T-shirt Kalıp Bilgisi : Regular Fit Manken Ölçüsü : Boy 1.88 cm / "
            "Göğüs 99 cm / Bel 77 cm / Kalça 97 cm / Beden L Üretim Yeri : Türkiye",
        ),
        (
            10581, "headwear",
            "<p>Модель демонстрируется на манекене ростом 1.89 м и весом 73 кг, который носит размер L.</p>",
        ),
    ],
)
def test_mannequin_measurements_are_not_sizes(pid, product_type, description):
    # Мерки и размер манекена — не размеры товара (ambiguous_variant_sizes у 6 логов).
    assert extract_sizes_from_input({"description": description}, product_type) == [], pid


def test_size_list_next_to_measurements_is_still_found():
    rows = extract_sizes_from_input(
        {"description": "Bedenler: S, M, L. Ürün boyu 70 cm, beden 42 için."}, "clothing"
    )
    assert [row["size"] for row in rows] == ["S", "M", "L", "42"]
