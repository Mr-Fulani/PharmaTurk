"""Словари для детерминированной локализации карточек (без LLM).

Ключи — турецкие (и встречающиеся в источниках английские) слова после
``fold()``: нижний регистр без турецких диакритик. Значения — RU/EN-формы.
Новые слова добавляются сюда, код правил не меняется.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

_FOLD = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a", "î": "i", "û": "u"})


def tr_lower(value: str | None) -> str:
    """Нижний регистр по-турецки: «İ» → «i», без комбинирующей точки («Si̇yah»)."""
    text = str(value or "").replace("İ", "i").replace("I", "ı").lower()
    return text.replace("̇", "")


def fold(value: str | None) -> str:
    """Ключ словаря: турецкий нижний регистр без диакритик, одиночные пробелы."""
    text = unicodedata.normalize("NFC", tr_lower(value)).translate(_FOLD)
    return re.sub(r"\s+", " ", text).strip()


# --- Русская грамматика: род существительного и согласование прилагательных ---

M, F, N, PL = "m", "f", "n", "pl"


def ru_adjective(masculine: str, gender: str) -> str:
    """Форма прилагательного по роду: «белый» → «белая/белое/белые»."""
    if masculine.startswith("="):  # несклоняемое («цвета хаки»)
        return masculine[1:]
    stem, ending = masculine[:-2], masculine[-2:]
    if gender == M or ending not in ("ый", "ий", "ой"):
        return masculine
    last = stem[-1:]
    if last in "кгх":
        forms = {F: "ая", N: "ое", PL: "ие"}
    elif last in "жшщч":
        forms = {F: "ая", N: "ое" if ending == "ой" else "ее", PL: "ие"}
    elif ending == "ий":
        forms = {F: "яя", N: "ее", PL: "ие"}
    else:
        forms = {F: "ая", N: "ое", PL: "ые"}
    return stem + forms[gender]


def ru_masculine(masculine: str) -> str:
    return masculine[1:] if masculine.startswith("=") else masculine


# --- Цвета ---
# fold-ключ → (RU прилагательное м. р. или «=несклоняемое», EN)
COLORS: dict[str, tuple[str, str]] = {
    "beyaz": ("белый", "White"),
    "kirik beyaz": ("молочный", "Off-white"),
    "kirli beyaz": ("молочный", "Off-white"),
    "kirli-beyaz": ("молочный", "Off-white"),
    "ekru": ("молочный", "Ecru"),
    "krem": ("кремовый", "Cream"),
    "siyah": ("черный", "Black"),
    "lacivert": ("темно-синий", "Navy"),
    "laci": ("темно-синий", "Navy"),
    "mavi": ("синий", "Blue"),
    "gri": ("серый", "Gray"),
    "antrasit": ("антрацитовый", "Anthracite"),
    "komur": ("темно-серый", "Charcoal"),
    "kahverengi": ("коричневый", "Brown"),
    "kahve": ("коричневый", "Brown"),
    "aci kahve": ("темно-коричневый", "Dark brown"),
    "taba": ("рыжий", "Tan"),
    "karamel": ("карамельный", "Caramel"),
    "bej": ("бежевый", "Beige"),
    "kum": ("песочный", "Sand"),
    "vizon": ("серо-бежевый", "Taupe"),
    "kirmizi": ("красный", "Red"),
    "bordo": ("бордовый", "Burgundy"),
    "pembe": ("розовый", "Pink"),
    "fusya": ("=цвета фуксии", "Fuchsia"),
    "mor": ("фиолетовый", "Purple"),
    "turuncu": ("оранжевый", "Orange"),
    "sari": ("желтый", "Yellow"),
    "yesil": ("зеленый", "Green"),
    "yag yesili": ("оливковый", "Olive"),
    "haki": ("=цвета хаки", "Khaki"),
    "indigo": ("=цвета индиго", "Indigo"),
    "altin": ("золотистый", "Gold"),
    "gumus": ("серебристый", "Silver"),
    "mat gumus": ("серебристый", "Matte silver"),
    "bronz": ("бронзовый", "Bronze"),
    "cok renkli": ("разноцветный", "Multicolor"),
    "kaplumbaga kabugu": ("черепаховый", "Tortoiseshell"),
    "kamuflaj": ("камуфляжный", "Camouflage"),
    "pudra": ("пудровый", "Powder pink"),
    "turkuaz": ("бирюзовый", "Turquoise"),
    "tas": ("серо-бежевый", "Stone"),
    "tas rengi": ("серо-бежевый", "Stone"),
    "nefti": ("темно-зеленый", "Dark green"),
    "melanj": ("меланжевый", "Melange"),
    "gri melanj": ("серый меланжевый", "Gray melange"),
    # FLO 27.10.2026: цвета, которые правила принимали за модель («Discovery Expedition Hardal»).
    "hardal": ("горчичный", "Mustard"),
    "mint": ("мятный", "Mint"),
    "saks": ("голубой", "Saxe blue"),
    "saks mavi": ("голубой", "Saxe blue"),
    "saks mavisi": ("голубой", "Saxe blue"),
    "petrol": ("=цвета петроль", "Petrol"),
    "petrol mavisi": ("=цвета петроль", "Petrol blue"),
    "petrol yesili": ("=цвета петроль", "Petrol green"),
    "renkli": ("разноцветный", "Multicolor"),
}
# Модификаторы оттенка: RU-префикс прилагательного, EN-слово. «yeni», «mat»,
# «orta» оттенок не меняют и пропускаются.
COLOR_MODIFIERS: dict[str, tuple[str, str]] = {
    "acik": ("светло-", "Light"),
    "koyu": ("темно-", "Dark"),
}
COLOR_NOISE = frozenset({"yeni", "mat", "orta", "rodeo"})
# «çeşitli» / «karışık asorti» — набор разных цветов: цвет в название не пишем.


@dataclass(frozen=True)
class Color:
    ru: str  # прилагательное м. р. (или «=несклоняемое»)
    en: str

    def ru_for(self, gender: str) -> str:
        return ru_adjective(self.ru, gender)


def clean_color_value(raw: str | None) -> str:
    """«Açık İndigo / S61986Z8 + 13 Renk Beden Seç…» → «Açık İndigo»."""
    text = str(raw or "").split("/")[0]
    text = re.split(r"\s\+\s|\bbeden\b|\brenk\b", text, flags=re.IGNORECASE)[0]
    return text.strip(" -,")


def translate_color(raw: str | None) -> Color | None:
    """Простой цвет с модификатором; составные («Siyah-Kahverengi») → None."""
    key = fold(clean_color_value(raw))
    if not key or key in ("none", "null"):
        return None
    if key in COLORS:
        return Color(*COLORS[key])
    words = [word for word in key.split() if word not in COLOR_NOISE]
    if not words:
        return None
    modifier = None
    if words[0] in COLOR_MODIFIERS and len(words) > 1:
        modifier = COLOR_MODIFIERS[words[0]]
        words = words[1:]
    base = COLORS.get(" ".join(words))
    if base is None:
        return None
    ru, en = base
    if modifier:
        if ru.startswith("="):
            return None
        ru = modifier[0] + ru
        en = f"{modifier[1]} {en.lower()}"
    return Color(ru, en)


# --- Пол / аудитория ---
# значение атрибута gender или слово названия → (RU прилагательное м. р., EN)
AUDIENCE: dict[str, tuple[str, str]] = {
    "men": ("мужской", "Men's"),
    "erkek": ("мужской", "Men's"),
    "women": ("женский", "Women's"),
    "kadin": ("женский", "Women's"),
    "kids": ("детский", "Kids'"),
    "cocuk": ("детский", "Kids'"),
    "erkek cocuk": ("детский", "Boys'"),
    "kiz cocuk": ("детский", "Girls'"),
    "bebek": ("детский", "Kids'"),
    "unisex": ("=унисекс", "Unisex"),
}


# --- Бренды мультибрендовых магазинов ---
# Бренд каталога — магазин, а настоящий бренд стоит первым в названии
# («Loris 50 ml Erkek Parfüm» на LC Waikiki).
STORE_BRANDS = frozenset({"lc waikiki"})
# Собственные линейки магазина («LCW ACCESSORIES», «LC WAIKIKI»): бренд остаётся.
STORE_OWN_LINE_PREFIXES = ("lcw", "lc waikiki")
# Слова линеек магазина («LCW ACCESSORIES», «LCW VISION»): в названии их заменяет бренд.
STORE_LINE_WORDS = frozenset({"lcw", "accessories", "vision", "casual", "young", "dream"})
# Общие слова названий Zara в ВЕРХНЕМ регистре, которых нет в словарях: «3'LÜ PAKET» —
# «3 шт.», «BOMBER CEKET» — «бомбер». Не модель (очередь модерации 27.10.2026).
GENERIC_NAME_WORDS = frozenset({"paket", "bomber"})
# Магазины, чьи названия — описание по-турецки без модели («Teknik naylon pantolon»):
# латинское слово до типа — не модель, а непереведённое слово (кроме кодов и ВЕРХНЕГО регистра).
DESCRIPTIVE_NAME_BRANDS = frozenset({"zara", "bershka", "pull&bear", "massimo dutti"})
# Слова с заглавной в начале названия, которые не бренд.
NOT_BRAND_WORDS = frozenset(
    {"yeni", "yazlik", "kislik", "klasik", "spor", "gunluk", "basic", "slim", "regular", "unisex", "set", "seti", "orijinal"}
)


# --- Типы товаров ---


@dataclass(frozen=True)
class Kind:
    ru: str  # существительное, нижний регистр
    gender: str  # род для согласования: m/f/n/pl
    en: str
    generic: bool = False  # «ayakkabı» уступает более точному типу в названии


def _k(ru: str, gender: str, en: str, generic: bool = False) -> Kind:
    return Kind(ru, gender, en, generic)


# Фразы (fold) → тип. Сопоставление ищет самую длинную фразу.
KINDS: dict[str, Kind] = {
    # одежда
    "tisort": _k("футболка", F, "T-Shirt"),
    "t-shirt": _k("футболка", F, "T-Shirt"),
    "t shirt": _k("футболка", F, "T-Shirt"),
    "tshirt": _k("футболка", F, "T-Shirt"),
    "tee": _k("футболка", F, "T-Shirt"),
    "spor tisort": _k("спортивная футболка", F, "Sports T-Shirt"),
    "polo": _k("поло", N, "Polo Shirt"),
    "polo tisort": _k("поло", N, "Polo Shirt"),
    "polo yaka tisort": _k("поло", N, "Polo Shirt"),
    "gomlek": _k("рубашка", F, "Shirt"),
    "pantolon": _k("брюки", PL, "Trousers"),
    "jean": _k("джинсы", PL, "Jeans"),
    "jeans": _k("джинсы", PL, "Jeans"),
    "kot pantolon": _k("джинсы", PL, "Jeans"),
    "sort": _k("шорты", PL, "Shorts"),
    "sweatshirt": _k("свитшот", M, "Sweatshirt"),
    "hoodie": _k("худи", N, "Hoodie"),
    "kapusonlu sweatshirt": _k("худи", N, "Hoodie"),
    "elbise": _k("платье", N, "Dress"),
    "etek": _k("юбка", F, "Skirt"),
    "ceket": _k("пиджак", M, "Jacket"),
    "mont": _k("куртка", F, "Jacket"),
    "kaban": _k("пальто", N, "Coat"),
    "yelek": _k("жилет", M, "Vest"),
    "hirka": _k("кардиган", M, "Cardigan"),
    "kazak": _k("свитер", M, "Sweater"),
    "atlet": _k("майка", F, "Tank Top"),
    "esofman alti": _k("спортивные брюки", PL, "Sweatpants"),
    "esofman takimi": _k("спортивный костюм", M, "Tracksuit"),
    "pijama takimi": _k("пижама", F, "Pajama Set"),
    "pijama takim": _k("пижама", F, "Pajama Set"),
    "pijama": _k("пижама", F, "Pajamas"),
    "bluz": _k("блузка", F, "Blouse"),
    "tunik": _k("туника", F, "Tunic"),
    "tayt": _k("леггинсы", PL, "Leggings"),
    # нижнее бельё
    "boxer": _k("трусы-боксеры", PL, "Boxers"),
    "slip": _k("трусы-слипы", PL, "Briefs"),
    "kulot": _k("трусы", PL, "Briefs"),
    "corap": _k("носки", PL, "Socks"),
    # обувь
    "sneaker": _k("кроссовки", PL, "Sneakers"),
    "high sneaker": _k("высокие кроссовки", PL, "High-Top Sneakers"),
    "spor ayakkabi": _k("кроссовки", PL, "Sneakers"),
    "kosu ayakkabisi": _k("беговые кроссовки", PL, "Running Shoes"),
    "sandalet": _k("сандалии", PL, "Sandals"),
    "sandal": _k("сандалии", PL, "Sandals"),
    "terlik": _k("шлепанцы", PL, "Slippers"),
    "terligi": _k("шлепанцы", PL, "Slippers"),
    "clog": _k("сабо", PL, "Clogs"),
    "deniz ayakkabisi": _k("аквашузы", PL, "Water Shoes"),
    "bot": _k("ботинки", PL, "Boots"),
    "cizme": _k("сапоги", PL, "Boots"),
    "loafer": _k("лоферы", PL, "Loafers"),
    "slip on": _k("слипоны", PL, "Slip-Ons"),
    "slip-on": _k("слипоны", PL, "Slip-Ons"),
    "babet": _k("балетки", PL, "Ballet Flats"),
    "ayakkabi": _k("обувь", F, "Shoes", generic=True),
    "ayakkabisi": _k("обувь", F, "Shoes", generic=True),
    # аксессуары
    "kemer": _k("ремень", M, "Belt"),
    "gunes gozlugu": _k("солнцезащитные очки", PL, "Sunglasses"),
    "pantolon askisi": _k("подтяжки", PL, "Suspenders"),
    "cuzdan": _k("кошелек", M, "Wallet"),
    "kartlik": _k("картхолдер", M, "Card Holder"),
    "canta": _k("сумка", F, "Bag"),
    "sirt cantasi": _k("рюкзак", M, "Backpack"),
    "atki": _k("шарф", M, "Scarf"),
    "eldiven": _k("перчатки", PL, "Gloves"),
    "kravat": _k("галстук", M, "Tie"),
    "papyon": _k("галстук-бабочка", F, "Bow Tie"),
    "saat": _k("часы", PL, "Watch"),
    # головные уборы
    "sapka": _k("головной убор", M, "Hat", generic=True),
    "kep": _k("кепка", F, "Cap"),
    "kep sapka": _k("кепка", F, "Cap"),
    "bere": _k("шапка", F, "Beanie"),
    "fotr sapka": _k("шляпа", F, "Fedora"),
    "bandana": _k("бандана", F, "Bandana"),
    # парфюмерия
    "edp": _k("парфюмерная вода", F, "Eau de Parfum"),
    "eau de parfum": _k("парфюмерная вода", F, "Eau de Parfum"),
    "edt": _k("туалетная вода", F, "Eau de Toilette"),
    "eau de toilette": _k("туалетная вода", F, "Eau de Toilette"),
    "edc": _k("одеколон", M, "Eau de Cologne"),
    "parfum": _k("парфюм", M, "Perfume", generic=True),
    "parfum seti": _k("парфюмерный набор", M, "Perfume Set"),
    "deodorant": _k("дезодорант", M, "Deodorant"),
    "roll-on": _k("шариковый дезодорант", M, "Roll-On Deodorant"),
    "roll on": _k("шариковый дезодорант", M, "Roll-On Deodorant"),
    "stick": _k("дезодорант-стик", M, "Deodorant Stick"),
    "roll-on ve stick": _k("дезодорант", M, "Deodorant"),
    "vucut spreyi": _k("спрей для тела", M, "Body Spray"),
}

# Тип по slug категории — когда в названии типа нет или он слишком общий.
CATEGORY_KINDS: dict[str, Kind] = {
    "t-shirts": KINDS["tisort"],
    "basic-tshirts": KINDS["tisort"],
    "polo-shirts": KINDS["polo"],
    "jeans": KINDS["jean"],
    "baggy-fit": KINDS["jean"],
    "sneakers": KINDS["sneaker"],
    "sandals": KINDS["sandalet"],
    "belts": KINDS["kemer"],
    "mens-classic-belts": KINDS["kemer"],
    "sunglasses": KINDS["gunes gozlugu"],
    "hw-caps": KINDS["kep"],
    "uw-mens-underwear": KINDS["boxer"],
    "burkini": _k("буркини", N, "Burkini"),
    # мебель: когда furniture_type нет в словаре
    "wardrobes": _k("гардероб", M, "Wardrobe"),
    "beds": _k("кровать", F, "Bed"),
    "armchairs": _k("кресло", N, "Armchair"),
    "dressers": _k("комод", M, "Chest of Drawers"),
    "sofas": _k("диван", M, "Sofa"),
    "day-beds": _k("кушетка", F, "Day-Bed"),
    "sofa-beds": _k("диван-кровать", M, "Sofa-Bed"),
    "coffee-tables": _k("журнальный столик", M, "Coffee Table"),
    "bed-bases": _k("основание кровати", N, "Bed Base"),
}

# Мебель IKEA: значение furniture_type (без названия серии) → тип.
FURNITURE_KINDS: dict[str, Kind] = {
    "gardirop": _k("гардероб", M, "Wardrobe"),
    "surgu kapakli gardirop": _k("гардероб с раздвижными дверцами", M, "Wardrobe with Sliding Doors"),
    "kose gardirop": _k("угловой гардероб", M, "Corner Wardrobe"),
    "acik gardirop": _k("открытый гардероб", M, "Open Wardrobe"),
    "cocuk gardirobu": _k("детский гардероб", M, "Children's Wardrobe"),
    "gardirop kapagi": _k("дверца для гардероба", F, "Wardrobe Door"),
    "gardirop iskeleti": _k("каркас гардероба", M, "Wardrobe Frame"),
    "surgu kapak": _k("раздвижная дверца", F, "Sliding Door"),
    "surgulu kapakli gomme dolap": _k("встроенный шкаф с раздвижными дверцами", M, "Built-in Wardrobe with Sliding Doors"),
    "dolap sistemi": _k("система хранения", F, "Storage System"),
    "dolap kombinasyonu": _k("комбинация для хранения", F, "Storage Combination"),
    "cift kisilik karyola": _k("двуспальная кровать", F, "Double Bed"),
    "cift kisilik karyola seti": _k("двуспальная кровать", F, "Double Bed Set"),
    "tek kisilik karyola": _k("односпальная кровать", F, "Single Bed"),
    "ranza": _k("двухъярусная кровать", F, "Bunk Bed"),
    "karyola latasi": _k("реечное дно кровати", N, "Slatted Bed Base"),
    "divan": _k("кушетка", F, "Day-Bed"),
    "3'lu kanepe": _k("трехместный диван", M, "3-Seat Sofa"),
    "2'li kanepe": _k("двухместный диван", M, "2-Seat Sofa"),
    "uzanma koltuklu 3'lu kanepe": _k("трехместный диван-реклайнер", M, "3-Seat Recliner Sofa"),
    "uzanma koltuklu 4'lu kanepe": _k("четырехместный диван-реклайнер", M, "4-Seat Recliner Sofa"),
    "2'li yatakli kanepe": _k("двухместный диван-кровать", M, "2-Seat Sofa-Bed"),
    "tekli koltuk": _k("кресло", N, "Armchair"),
    "uzanma koltugu": _k("кресло-реклайнер", N, "Recliner"),
    "rattan koltuk": _k("кресло из ротанга", N, "Rattan Armchair"),
    "raf": _k("полка", F, "Shelf"),
    "cekmece": _k("ящик", M, "Drawer"),
    "rayli cekmece": _k("выдвижной ящик", M, "Pull-out Drawer"),
    "tel sepet": _k("проволочная корзина", F, "Wire Basket"),
    "rayli tel sepet": _k("проволочная корзина с направляющими", F, "Wire Basket with Pull-out Rail"),
    "aski borusu": _k("штанга для одежды", F, "Clothes Rail"),
    "ayarlanabilir aski borusu": _k("регулируемая штанга для одежды", F, "Adjustable Clothes Rail"),
    "acik dolap": _k("открытый шкаф", M, "Open Wardrobe"),
    "dolap": _k("шкаф", M, "Cabinet"),
    "cocuk dolabi": _k("детский шкаф", M, "Children's Wardrobe"),
    "duvar dolabi": _k("навесной шкаф", M, "Wall Cabinet"),
    "cocuk dolap kombinasyonu": _k("детская комбинация для хранения", F, "Children's Storage Combination"),
    "kapakli gardirop iskeleti": _k("каркас гардероба с дверцами", M, "Wardrobe Frame with Doors"),
    "kapakli gardirop yukseltme unitesi": _k("надставка для гардероба с дверцами", F, "Wardrobe Add-on Unit with Doors"),
    "surgu kapak iskeleti": _k("рама раздвижной дверцы", F, "Sliding Door Frame"),
    "surgulu raf": _k("выдвижная полка", F, "Pull-out Shelf"),
    "bolmeli surgulu raf": _k("выдвижная полка с отделениями", F, "Pull-out Shelf with Compartments"),
    "surgulu raf ici duzenleyici": _k("выдвижной органайзер для полки", M, "Pull-out Shelf Organiser"),
    "raf ici bolmeli unite": _k("вставка с отделениями", F, "Shelf Insert with Compartments"),
    "dolap ici raf": _k("полка для шкафа", F, "Cabinet Shelf"),
    "cam raf": _k("стеклянная полка", F, "Glass Shelf"),
    "ayakkabi rafi": _k("полка для обуви", F, "Shoe Shelf"),
    "surgulu ayakkabi rafi": _k("выдвижная полка для обуви", F, "Pull-out Shoe Shelf"),
    "surgulu pantolon askisi": _k("выдвижная вешалка для брюк", F, "Pull-out Trouser Hanger"),
    "cekilebilir aski": _k("выдвижная вешалка", F, "Pull-out Hanger"),
    "cok amacli aski": _k("многофункциональная вешалка", F, "Multi-use Hanger"),
    "ayakli askilik": _k("напольная вешалка", F, "Clothes Stand"),
    "asma rayi": _k("рейка для подвешивания", F, "Suspension Rail"),
    "sepet rayi": _k("направляющие для корзины", PL, "Basket Rail"),
    "gardirop ici sepet rayi": _k("направляющие для корзины в гардероб", PL, "Wardrobe Basket Rail"),
    "cekmece on paneli": _k("фасад ящика", M, "Drawer Front"),
    "on panelsiz cekmece": _k("ящик без фасада", M, "Drawer without Front"),
    "cam panelli cekmece": _k("ящик со стеклянной панелью", M, "Drawer with Glass Front"),
    "cekmece ortusu": _k("коврик для ящика", M, "Drawer Mat"),
    "frenli mentese": _k("петля с плавным закрыванием", F, "Soft-closing Hinge"),
    "cocuk sifonyeri": _k("детский комод", M, "Children's Chest of Drawers"),
    "karyola cekmecesi": _k("ящик для кровати", M, "Bed Storage Box"),
    "karyola kilifi": _k("чехол для кровати", M, "Bed Frame Cover"),
    "ayarlanabilir karyola latasi": _k("регулируемое реечное дно кровати", N, "Adjustable Slatted Bed Base"),
    "bebek karyolasi": _k("детская кроватка", F, "Cot"),
    "besik": _k("колыбель", F, "Cradle"),
    "bebek mobilya seti": _k("комплект детской мебели", M, "Baby Furniture Set"),
    "yatak basi": _k("изголовье кровати", N, "Headboard"),
    "sallanan koltuk": _k("кресло-качалка", N, "Rocking Chair"),
    "sallanan koltuk iskeleti": _k("каркас кресла-качалки", M, "Rocking Chair Frame"),
    "tekli koltuk kilifi": _k("чехол для кресла", M, "Armchair Cover"),
    "tekli koltuk ve puf": _k("кресло с пуфом", N, "Armchair and Footstool"),
    # Реклайнер (кресло с откидной спинкой), не кресло-кровать: «Кресло-кровать IKEA
    # EKOLSUND» в «Креслах» давало конфликт с «Кроватями» (очередь модерации 27.10.2026).
    "yatar koltuk": _k("кресло-реклайнер", N, "Recliner Armchair"),
    "kose koltuk": _k("угловой диван", M, "Corner Sofa"),
    "kose kanepe": _k("угловой диван", M, "Corner Sofa"),
    "3'lu kose kanepe": _k("трехместный угловой диван", M, "3-Seat Corner Sofa"),
    "4'lu kose kanepe": _k("четырехместный угловой диван", M, "4-Seat Corner Sofa"),
    "5'li kose kanepe": _k("пятиместный угловой диван", M, "5-Seat Corner Sofa"),
    "6'li kose kanepe": _k("шестиместный угловой диван", M, "6-Seat Corner Sofa"),
    "uzanma koltuklu 5'li kose kanepe": _k("пятиместный угловой диван-реклайнер", M, "5-Seat Corner Recliner Sofa"),
    "bazali yatakli kose kanepe": _k("угловой диван-кровать с ящиком", M, "Corner Sofa-Bed with Storage"),
    "2'li moduler kanepe": _k("двухместный модульный диван", M, "2-Seat Modular Sofa"),
    "4'lu moduler kanepe": _k("четырехместный модульный диван", M, "4-Seat Modular Sofa"),
    "6'li moduler kanepe": _k("шестиместный модульный диван", M, "6-Seat Modular Sofa"),
    "4'lu moduler kose kanepe": _k("четырехместный модульный угловой диван", M, "4-Seat Modular Corner Sofa"),
    "3'lu yatakli kanepe": _k("трехместный диван-кровать", M, "3-Seat Sofa-Bed"),
    "3'lu deri kanepe": _k("трехместный кожаный диван", M, "3-Seat Leather Sofa"),
    "7'li u kanepe": _k("семиместный П-образный диван", M, "7-Seat U-Shaped Sofa"),
    "ek kose unitesi": _k("угловая секция", F, "Corner Section"),
    "tekli oturma unitesi": _k("одноместная секция", F, "1-Seat Section"),
    "2'li oturma unitesi": _k("двухместная секция", F, "2-Seat Section"),
    "ayak uzatma taburesi": _k("табурет для ног", M, "Footstool"),
    "ayak uzatma taburesi minderi": _k("подушка для табурета для ног", F, "Footstool Cushion"),
    "sallanan koltuk ve ayak uzatma taburesi": _k("кресло-качалка с табуретом для ног", N, "Rocking Chair and Footstool"),
    "puf": _k("пуф", M, "Pouffe"),
    "saklama gozlu puf": _k("пуф с отделением для хранения", M, "Pouffe with Storage"),
    "yan sehpa": _k("приставной столик", M, "Side Table"),
    "tepsili sehpa": _k("столик-поднос", M, "Tray Table"),
    "mutfak adasi": _k("кухонный остров", M, "Kitchen Island"),
    "calisma tezgahi": _k("рабочий стол", M, "Workbench"),
    "cocuk kitapligi": _k("детский книжный шкаф", M, "Children's Bookcase"),
}
# «3 çekmeceli şifonyer» → «комод с 3 ящиками»
FURNITURE_DRAWER_CHEST_RE = re.compile(r"^(\d+) cekmeceli sifonyer$")

# Цвета/отделки мебели (части через «-»): RU м. р. без согласования, как у IKEA.
FURNITURE_FINISHES: dict[str, tuple[str, str]] = {
    "meşe": ("дуб", "oak"),
    "meşe görünümlü": ("под дуб", "oak effect"),
    "meşe kaplama": ("дубовый шпон", "oak veneer"),
    "ağartılmış meşe görünümlü": ("под беленый дуб", "white stained oak effect"),
    "ağartılmış meşe kaplama": ("беленый дубовый шпон", "white stained oak veneer"),
    "çam": ("сосна", "pine"),
    "huş": ("береза", "birch"),
    "venge": ("венге", "wenge"),
    "ceviz": ("орех", "walnut"),
    "ayna": ("зеркало", "mirror"),
    "aynalı cam": ("зеркальное стекло", "mirror glass"),
    "cam": ("стекло", "glass"),
}


# --- Описательные слова названий ---
# fold-фраза → (RU постпозитивная фраза, EN-префикс). Пустые значения — слово
# допустимо, но в название не выносится.
DESCRIPTORS: dict[str, tuple[str, str]] = {
    "bisiklet yaka": ("с круглым вырезом", "Crew Neck"),
    "crew neck": ("с круглым вырезом", "Crew Neck"),
    "cneck": ("с круглым вырезом", "Crew Neck"),
    "yuvarlak yaka": ("с круглым вырезом", "Crew Neck"),
    "v yaka": ("с V-образным вырезом", "V-Neck"),
    "v-neck": ("с V-образным вырезом", "V-Neck"),
    "polo yaka": ("с отложным воротником", "Polo Collar"),
    "kisa kollu": ("с коротким рукавом", "Short Sleeve"),
    "uzun kollu": ("с длинным рукавом", "Long Sleeve"),
    "kolsuz": ("без рукавов", "Sleeveless"),
    "baskili": ("с принтом", "Printed"),
    "logo baskili": ("с логотипом", "Logo"),
    "logolu": ("с логотипом", "Logo"),
    "desenli": ("с узором", "Patterned"),
    "cizgili": ("в полоску", "Striped"),
    "kapusonlu": ("с капюшоном", "Hooded"),
    "nakisli": ("с вышивкой", "Embroidered"),
    "relaxed": ("свободного кроя", "Relaxed Fit"),
    "loose fit": ("свободного кроя", "Loose Fit"),
    "rahat kalip": ("свободного кроя", "Relaxed Fit"),
    "regular kalip": ("прямого кроя", "Regular Fit"),
    "standart kalip": ("прямого кроя", "Regular Fit"),
    "slim kalip": ("приталенного кроя", "Slim Fit"),
    "oversize kalip": ("оверсайз", "Oversize"),
    "buyuk beden": ("большого размера", "Plus Size"),
    "yazi baskili": ("с надписью", "Slogan"),
    "yazili": ("с надписью", "Slogan"),
    "jakarli": ("из жаккарда", "Jacquard"),
    "cizgi": ("с полосками", "Striped"),
    "graphic": ("с принтом", "Graphic"),
    "logo": ("с логотипом", "Logo"),
    "short sleeve": ("с коротким рукавом", "Short Sleeve"),
    "long sleeve": ("с длинным рукавом", "Long Sleeve"),
    "ortopetik": ("с ортопедической стелькой", "Orthopedic"),
    "ortapedik": ("с ортопедической стелькой", "Orthopedic"),
    "orto pedik": ("с ортопедической стелькой", "Orthopedic"),
    "ortopedik taban": ("с ортопедической стелькой", "Orthopedic"),
    "kaymaz": ("с нескользящей подошвой", "Non-Slip"),
    "kaymaz taban": ("с нескользящей подошвой", "Non-Slip"),
    "isikli": ("со светящейся подошвой", "Light-Up"),
    "lastikli": ("на резинке", "Elastic"),
    "kapali burun": ("с закрытым носком", "Closed-Toe"),
    "dikdortgen": ("прямоугольной формы", "Rectangular"),
    "metal": ("из металла", "Metal"),
    "asetat": ("из ацетата", "Acetate"),
    "oval": ("овальной формы", "Oval"),
    "yuvarlak": ("круглой формы", "Round"),
    "fit": ("", ""),
    "canlandirici": ("", ""),
    "tanimsiz": ("", ""),
    "nemlendirici": ("с увлажняющим эффектом", "Moisturizing"),
    "fermuar detayli": ("с молнией", "Zip Detail"),
    "fermuarli": ("с молнией", "Zip"),
    "yirtik detayli": ("с потертостями", "Distressed"),
    "karisik": ("", ""),  # «Karışık» — набор цветов: цвет в название не пишем
    "asorti": ("", ""),
    "cift yonlu": ("", ""),
    "noos": ("", ""),
    "ter karsiti": ("против пота", "Antiperspirant"),
    "leke karsiti": ("против следов", "Anti-Marks"),
    "cift tokali": ("с двумя пряжками", "Double-Buckle"),
    "penye": ("из трикотажа", "Jersey"),
    "ss": ("", ""),
    "cn": ("", ""),
    "pls": ("большого размера", "Plus Size"),
    "kalip": ("", ""),
    "kesim": ("", ""),
    "detayli": ("", ""),
    "yumusak": ("", ""),
    "dokulu": ("", ""),
    "flamli": ("", ""),
    "comfort": ("", ""),
    "esnek": ("", ""),
    "taban": ("", ""),
    "tabanli": ("", ""),
    "doktor tavsiyeli": ("", ""),
    "dr. tavsiyeli": ("", ""),
    "d.r tavsiyeli": ("", ""),
    "topuk jelli": ("", ""),
    "poplin": ("из поплина", "Poplin"),
    "kombin": ("", ""),
    "cesitli": ("", ""),
    "regular fit": ("прямого кроя", "Regular Fit"),
    "standart fit": ("прямого кроя", "Regular Fit"),
    "relaxed fit": ("свободного кроя", "Relaxed Fit"),
    "rahat kesim": ("свободного кроя", "Relaxed Fit"),
    "oversize": ("оверсайз", "Oversize"),
    "slim fit": ("приталенного кроя", "Slim Fit"),
    "dar kesim": ("приталенного кроя", "Slim Fit"),
    "pamuk": ("из хлопка", "Cotton"),
    "pamuklu": ("из хлопка", "Cotton"),
    "hakiki deri": ("из натуральной кожи", "Genuine Leather"),
    "gercek deri": ("из натуральной кожи", "Genuine Leather"),
    "deri": ("из кожи", "Leather"),
    "suni deri": ("из искусственной кожи", "Faux Leather"),
    "nubuk": ("из нубука", "Nubuck"),
    "suet": ("из замши", "Suede"),
    "ortopedik": ("с ортопедической стелькой", "Orthopedic"),
    "ortopedik tabanli": ("с ортопедической стелькой", "Orthopedic"),
    "anatomik": ("с анатомической стелькой", "Anatomic"),
    "cirtli": ("на липучке", "Velcro"),
    "bagcikli": ("на шнурках", "Lace-Up"),
    "tokali": ("с пряжкой", "Buckle"),
    # допустимые, но не выносимые в название
    "gunluk": ("", ""),
    "hafif": ("", ""),
    "yazlik": ("", ""),
    "klasik": ("", ""),
    "basic": ("", ""),
    "duz": ("", ""),
    "standart": ("", ""),
    "normal": ("", ""),
    "rahat": ("", ""),
    "spor": ("", ""),
    "ve": ("", ""),
    "ile": ("", ""),
    "model": ("", ""),
    "yeni": ("", ""),
}

# Турецкие слова словарей, которые LLM копирует в название как есть («Мужские сандалии
# Siyah Lastikli», «Kum Nubuk»): в названии правилами их нет, значит, это брак (партия FLO 27.10.2026).
# Слова, совпадающие с английскими («Basic», «Logo», «Polo»), не считаются.
_ENGLISH_VOCAB_WORDS = frozenset(
    {
        "bandana", "basic", "boxer", "clog", "cn", "cneck", "comfort", "deodorant", "edc", "edp", "edt",
        "fit", "graphic", "hoodie", "indigo", "jean", "jeans", "kids", "loafer", "logo", "men", "metal",
        "mint", "model", "noos", "normal", "oval", "oversize", "parfum", "petrol", "pls", "polo", "poplin", "relaxed",
        "sandal", "slip", "sneaker", "ss", "stick", "sweatshirt", "tee", "tshirt", "unisex", "women",
    }
)
TURKISH_TITLE_WORDS = frozenset(
    key
    for mapping in (COLORS, DESCRIPTORS, AUDIENCE, KINDS)
    for key in mapping
    if " " not in key and "-" not in key and key not in _ENGLISH_VOCAB_WORDS
)

# Канонический материал аксессуара (RU из attribute_specs) → фраза названия.
MATERIAL_PHRASES: dict[str, tuple[str, str]] = {
    "натуральная кожа": ("из натуральной кожи", "Genuine Leather"),
    "искусственная кожа": ("из искусственной кожи", "Faux Leather"),
    "металл": ("из металла", "Metal"),
    "хлопок": ("из хлопка", "Cotton"),
    "текстиль": ("из текстиля", "Textile"),
}

# Материал аксессуара из строки источника «Kumaş: Suni Deri» / «Kumaş Karışımı: 100% Deri»
# (fold) → канон attribute_specs. Сильнее атрибута парсера: тот ищет слово по всему тексту
# и у ремня с металлической пряжкой находил «metal».
ACCESSORY_MATERIALS: dict[str, str] = {
    "suni deri": "Искусственная кожа",
    "vegan deri": "Искусственная кожа",
    "hakiki deri": "Натуральная кожа",
    "gercek deri": "Натуральная кожа",
    "deri": "Натуральная кожа",
    "metal": "Металл",
    "pamuk": "Хлопок",
    "tekstil": "Текстиль",
}

# Служебные куски названий магазинов: «Kemer - Markalar - 799,00 TL».
TITLE_NOISE_RE = re.compile(
    r"\s+-\s+(?:markalar|lc\s*waikiki)\b|\bmarkalar\b|\(\s*\d+(?:[.,]\d+)?\s*fl\.?\s*oz\.?\s*\)",
    re.IGNORECASE,
)

# Состав / материал: fold-слово → (RU сущ. в им. п., EN)
FIBERS: dict[str, tuple[str, str]] = {
    "pamuk": ("хлопок", "cotton"),
    "organik pamuk": ("органический хлопок", "organic cotton"),
    "polyester": ("полиэстер", "polyester"),
    "poliester": ("полиэстер", "polyester"),
    "elastan": ("эластан", "elastane"),
    "likra": ("лайкра", "lycra"),
    "viskon": ("вискоза", "viscose"),
    "modal": ("модал", "modal"),
    "keten": ("лен", "linen"),
    "yun": ("шерсть", "wool"),
    "naylon": ("нейлон", "nylon"),
    "poliamid": ("полиамид", "polyamide"),
    "akrilik": ("акрил", "acrylic"),
    "deri": ("кожа", "leather"),
    "hakiki deri": ("натуральная кожа", "genuine leather"),
    "suni deri": ("искусственная кожа", "faux leather"),
    "poliuretan": ("полиуретан", "polyurethane"),
}
# Материалы обуви (верх, подкладка, подошва) — коды FLO через «/».
SHOE_MATERIALS: dict[str, tuple[str, str]] = {
    "tekstil": ("текстиль", "textile"),
    "pu": ("полиуретан", "polyurethane"),
    "pvc": ("ПВХ", "PVC"),
    "mesh": ("сетка", "mesh"),
    "kanvas": ("канвас", "canvas"),
    "suni deri": ("искусственная кожа", "faux leather"),
    "deri": ("натуральная кожа", "genuine leather"),
    "hakiki deri": ("натуральная кожа", "genuine leather"),
    "deri (sigir)": ("натуральная кожа (говяжья)", "genuine leather (cowhide)"),
    "deri (dana)": ("натуральная кожа (телячья)", "genuine leather (calfskin)"),
    "deri (inek)": ("натуральная кожа (коровья)", "genuine leather (cowhide)"),
    "deri (keci)": ("натуральная кожа (козья)", "genuine leather (goatskin)"),
    "suet (inek)": ("замша", "suede"),
    "nubuk": ("нубук", "nubuck"),
    "kaucuk": ("резина", "rubber"),
    "phylon": ("филон", "Phylon"),
    "termo": ("термопластик", "thermoplastic"),
    "eva": ("ЭВА", "EVA"),
    "tpr": ("термопластичная резина", "TPR"),
    "tpu": ("термополиуретан", "TPU"),
    "poli": ("полимер", "polymer"),
}


def translate_composition(raw: str | None) -> tuple[str, str] | None:
    """«%100 PAMUK» / «%95 Pamuk %5 Elastan» → («100% хлопок», «100% cotton»)."""
    text = fold(raw)
    parts = re.findall(r"%\s*(\d{1,3})\s+([a-z ]+?)(?=\s*%|,|$)", text)
    if not parts:
        return None
    ru_parts, en_parts = [], []
    for percent, fiber in parts:
        name = FIBERS.get(fiber.strip())
        if name is None:
            return None
        ru_parts.append(f"{percent}% {name[0]}")
        en_parts.append(f"{percent}% {name[1]}")
    return ", ".join(ru_parts), ", ".join(en_parts)


def translate_shoe_material(raw: str | None) -> tuple[str, str] | None:
    """«TEKSTIL/PU» → («текстиль, полиуретан», «textile, polyurethane»)."""
    text = fold(raw)
    if not text or text in ("diger", "none"):
        return None
    ru_parts, en_parts = [], []
    for part in (piece.strip() for piece in text.split("/")):
        part = part.replace("pu kaplamali ", "")
        name = SHOE_MATERIALS.get(part)
        if name is None:
            return None
        if name[0] not in ru_parts:
            ru_parts.append(name[0])
            en_parts.append(name[1])
    return ", ".join(ru_parts), ", ".join(en_parts)


def translate_furniture_finish(raw: str | None) -> tuple[str, str] | None:
    """«beyaz-aynalı cam» → («белый/зеркальное стекло», «white/mirror glass»).

    Части без перевода (название ткани «Axvall» и т.п. латиницей с заглавной)
    сохраняются как есть; неизвестное турецкое слово → None.
    """
    text = str(raw or "").strip()
    if not text:
        return None
    ru_parts, en_parts = [], []
    for part in (piece.strip() for piece in text.split("-")):
        lowered = tr_lower(part)
        finish = FURNITURE_FINISHES.get(lowered)
        if finish:
            ru_parts.append(finish[0])
            en_parts.append(finish[1])
            continue
        words = part.split()
        fabric = []
        while words and words[0][:1].isupper() and words[0].isascii() and len(words) > 1:
            fabric.append(words.pop(0))
        color = translate_color(" ".join(words))
        if color is None:
            return None
        prefix = " ".join(fabric)
        ru_parts.append(f"{prefix} {ru_masculine(color.ru)}".strip())
        en_parts.append(f"{prefix} {color.en.lower()}".strip())
    return "/".join(ru_parts), "/".join(en_parts)


@lru_cache(maxsize=1)
def generic_title_words() -> frozenset[str]:
    """Словарные слова (тип, цвет, пол, описание) и линейки магазина — не бренд/модель.

    Слова из фраз тоже: «GÜNEŞ GÖZLÜĞÜ» в названии Zara — тип, а не модель.
    """
    words = set()
    for mapping in (KINDS, COLORS, AUDIENCE, DESCRIPTORS, COLOR_MODIFIERS):
        for key in mapping:
            words.update(key.split())
    return frozenset(words | COLOR_NOISE | STORE_LINE_WORDS | GENERIC_NAME_WORDS)
