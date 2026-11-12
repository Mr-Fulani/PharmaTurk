"""Парсер SuperStep (superstep.com.tr) — мультибрендовая обувь, одежда и аксессуары.

Сайт работает на платформе Akinon; обход раздела, карточка, цены, размеры и
проверка наличия — в общем ``AkinonParser`` (``akinon.py``). Здесь — только своё:
раскладка по нашим разделам по подгруппе ``integration_alt_grup``
(``SUPERSTEP_SUBGROUP_CATEGORIES``) с поправками по названию и бренду. Товар
неизвестной подгруппы не загружается и попадает в отчёт прогона «не разложено».
"""

from typing import Any, Dict, Sequence, Tuple

from ..base.utils import clean_text
from .akinon import AkinonFormatError, AkinonParser, akinon_key

# Прежние имена: на них ссылаются команды переноса товаров и тесты.
SuperstepFormatError = AkinonFormatError
superstep_subgroup_key = akinon_key


def _by_gender(
    women: Sequence[str],
    men: Sequence[str],
    other: Sequence[str],
    kids: Sequence[str] = (),
    boys: Sequence[str] = (),
    girls: Sequence[str] = (),
) -> Dict[str, Tuple[str, ...]]:
    """Маршрут по полу; ``boys``/``girls`` — детям по ``integration_erp_cinsiyet``."""
    routes = {"women": tuple(women), "men": tuple(men), "": tuple(other)}
    for key, route in (("kids", kids), ("boys", boys), ("girls", girls)):
        if route:
            routes[key] = tuple(route)
    return routes


_KIDS_UNDERWEAR = ("uw-children-underwear", "underwear")


_BAGS = ("bags-wallets", "accessories")

# Подгруппа SuperStep → наши разделы: первый существующий в каталоге slug
# (дальше — родитель и корень). У сумок наш раздел зависит от пола.
SUPERSTEP_SUBGROUP_CATEGORIES: Dict[str, Any] = {
    # Обувь
    "spor ayakkabi & sneaker": ("sneakers", "shoes"),
    "kosu ayakkabisi": ("running-shoes", "sneakers", "shoes"),
    "basketbol ayakkabisi": ("basketball-shoes", "sneakers", "shoes"),
    "antrenman ayakkabisi": ("training-shoes", "sneakers", "shoes"),
    "tenis ayakkabisi": ("training-shoes", "sneakers", "shoes"),
    "voleybol ayakkabisi": ("training-shoes", "sneakers", "shoes"),
    "krampon": ("training-shoes", "sneakers", "shoes"),
    "hali saha kramponu": ("training-shoes", "sneakers", "shoes"),
    "outdoor ayakkabi": ("sneakers", "shoes"),
    "terlik": ("slides", "sandals", "shoes"),
    "sandalet": ("sandals-classic", "sandals", "shoes"),
    "havuz & deniz ayakkabisi": ("sandals", "shoes"),
    "bot": ("boots", "shoes"),
    "bot & cizme": ("boots", "shoes"),
    "babet": ("casual-shoes", "shoes"),
    "gunluk ayakkabi": ("casual-shoes", "shoes"),
    # Одежда
    "t-shirt": ("t-shirts", "tops", "clothing"),
    "polo": ("polo-shirts", "t-shirts", "tops", "clothing"),
    "forma": ("t-shirts", "tops", "clothing"),
    "atlet": ("tank-tops", "tops", "clothing"),
    "crop": ("crop-tops", "tops", "clothing"),
    "body": ("tops-items", "tops", "clothing"),
    "gomlek": ("shirts", "tops", "clothing"),
    "sweatshirt": ("hoodies", "knitwear", "clothing"),
    "hoodie": ("hoodies", "knitwear", "clothing"),
    "polar": ("fleece", "knitwear", "clothing"),
    "triko": ("sweaters", "knitwear", "clothing"),
    "kazak": ("sweaters", "knitwear", "clothing"),
    "suveter": ("sweaters", "knitwear", "clothing"),
    "hirka": ("cardigans", "knitwear", "clothing"),
    "sort": ("shorts", "bottoms", "clothing"),
    "deniz sortu": ("shorts", "bottoms", "clothing"),
    "mayo & mayo sort": ("shorts", "bottoms", "clothing"),
    "pantolon": ("pants", "bottoms", "clothing"),
    "esofman alti": ("pants", "bottoms", "clothing"),
    "jean": ("jeans", "bottoms", "clothing"),
    "tayt": ("leggings", "bottoms", "clothing"),
    "etek": ("skirts", "bottoms", "clothing"),
    "elbise": ("dresses", "clothing"),
    "esofman ustu": ("jackets", "outerwear", "clothing"),
    "esofman takimi": ("tracksuits", "suits", "clothing"),
    "esofman": ("tracksuits", "suits", "clothing"),
    "ceket": ("jackets", "outerwear", "clothing"),
    "mont": ("jackets", "outerwear", "clothing"),
    "yelek": ("vests", "outerwear", "clothing"),
    "yagmurluk": ("windbreakers", "jackets", "outerwear", "clothing"),
    "ruzgarlik": ("windbreakers", "jackets", "outerwear", "clothing"),
    "tulum": ("clothing",),
    "pijama takimi": ("pajamas", "sleepwear", "clothing"),
    # Купальников в одежде нет — до своего раздела идут в корень «Одежда».
    "bikini": ("clothing",),
    "bikini & mayo": ("clothing",),
    # Бельё
    "boxer": _by_gender(
        *[("uw-boxers", "uw-mens-underwear", "underwear")] * 3,
        kids=_KIDS_UNDERWEAR,
        boys=("uw-boys-briefs", "uw-boys-underwear", *_KIDS_UNDERWEAR),
        girls=("uw-girls-panties", "uw-girls-underwear", *_KIDS_UNDERWEAR),
    ),
    "ic giyim": _by_gender(
        ("uw-womens-underwear", "underwear"),
        ("uw-mens-underwear", "underwear"),
        ("underwear",),
        kids=_KIDS_UNDERWEAR,
        boys=("uw-boys-underwear", *_KIDS_UNDERWEAR),
        girls=("uw-girls-underwear", *_KIDS_UNDERWEAR),
    ),
    "bra": _by_gender(
        *[("uw-sports-bras", "uw-bras", "underwear")] * 3,
        kids=("uw-girls-underwear", *_KIDS_UNDERWEAR),
    ),
    "bra & spor sutyeni": _by_gender(
        *[("uw-sports-bras", "uw-bras", "underwear")] * 3,
        kids=("uw-girls-underwear", *_KIDS_UNDERWEAR),
    ),
    "corap": ("uw-socks", "uw-socks-hosiery", "underwear"),
    # Головные уборы
    "sapka": _by_gender(
        *[("hw-baseball-caps", "hw-caps", "headwear")] * 3,
        kids=("hw-childrens-caps", "hw-children-headwear", "headwear"),
    ),
    "bere": _by_gender(
        *[("hw-beanies", "hw-winter-headwear", "headwear")] * 3,
        kids=("hw-childrens-beanies", "hw-children-headwear", "headwear"),
    ),
    # Аксессуары
    "sirt cantasi": _by_gender(
        ("acc-womens-backpacks", "womens-bags", *_BAGS),
        ("acc-mens-backpacks", "mens-bags", *_BAGS),
        ("backpacks", *_BAGS),
    ),
    "bel cantasi": _by_gender(
        ("acc-belt-bags", "womens-bags", *_BAGS),
        ("acc-mens-belt-bags", "mens-bags", *_BAGS),
        _BAGS,
    ),
    "omuz cantasi": _by_gender(("shoulder-bags", "womens-bags", *_BAGS), _BAGS, _BAGS),
    "el cantasi": _by_gender(("womens-bags", *_BAGS), _BAGS, _BAGS),
    "postaci cantasi": ("messenger-bags", "mens-bags", *_BAGS),
    "canta": _BAGS,
    "spor cantasi": _BAGS,
    "seyahat cantasi": ("duffle-bags", "travel-bags", *_BAGS),
    "valiz": ("suitcases", "travel-bags", *_BAGS),
    "cuzdan": ("wallets", *_BAGS),
    "cuzdan & kartlik": ("wallets", *_BAGS),
    "kalem kutusu": ("accessories",),
    "anahtarlik": ("accessories",),
    "ayakkabi bakim urunu": ("accessories",),
    "bileklik": ("accessories",),
    "saat": ("watches", "accessories"),
    "atki": ("scarves", "scarves-shawls", "accessories"),
    "boyunluk": ("snoods", "scarves-shawls", "accessories"),
    "eldiven": ("acc-gloves", "accessories"),
    "sac bandi": ("acc-headbands", "hair-accessories", "accessories"),
    # Лыжные перчатки — одежда, а не снаряд (решение владельца 11.11.2026).
    "kayak eldiveni": ("acc-gloves", "accessories"),
    # Спорттовары — только снаряды и предметы. Раздел маршрута под чужим корнем сервис
    # пропускает (``route_categories``): ``tracksuits`` лежал под «Спорттоварами».
    "basketbol topu": ("basketball-balls", "basketball", "team-sports", "sports"),
    "dizlik": ("sports",),
    "kolluk": ("sports",),
    "tekmelik": ("shin-guards", "football", "team-sports", "sports"),
    "yuzucu gozlugu": ("swimming-goggles", "swimming", "water-sports", "sports"),
    "yuzme aksesuari": ("swimming", "water-sports", "sports"),
    "spor aksesuarlari": ("fitness-accessories", "fitness-gym", "sports"),
    "antrenman aksesuari": ("fitness-accessories", "fitness-gym", "sports"),
    "havlu": ("sports",),
    # Посуда
    "termos": ("thermoses", "drinkware", "tableware"),
    "suluk": ("thermoses", "drinkware", "tableware"),
}

# Решение владельца 04.11.2026: фигурки (Funko, Bearbrick), шахматы и
# служебная группа «281» не загружаются, даже если для них появится раздел.
SUPERSTEP_SKIPPED_SUBGROUPS = frozenset({"figur", "satranc takimi", "281"})


# Окончания названий товара, которые не совпадают с подгруппой дословно.
SUPERSTEP_NAME_SUBGROUPS = {
    "sneaker": "spor ayakkabi & sneaker",
    "spor ayakkabi": "spor ayakkabi & sneaker",
    "sporcu sutyeni": "bra & spor sutyeni",
}


def superstep_subgroup_from_name(name: Any) -> str:
    """Подгруппа по окончанию названия — подписью, как у сайта
    («… Kadın Yeşil T-Shirt» → «T-Shirt»).

    Нужна товарам маркетплейса без ``integration_alt_grup``: тип товара в
    названии SuperStep всегда в конце. Самое длинное совпадение побеждает
    («Deniz Şortu» раньше «Şort»).
    """
    words = clean_text(str(name or "")).split()
    text = superstep_subgroup_key(" ".join(words))
    endings = {*SUPERSTEP_SUBGROUP_CATEGORIES, *SUPERSTEP_SKIPPED_SUBGROUPS, *SUPERSTEP_NAME_SUBGROUPS}
    for ending in sorted(endings, key=len, reverse=True):
        if text == ending or text.endswith(" " + ending):
            return " ".join(words[-len(ending.split()):])
    return ""


def resolve_superstep_category_slugs(subgroup: Any, gender: str = "", kids_gender: str = "") -> Tuple[str, ...]:
    """Разделы подгруппы (от точного к корню); пусто — подгруппа не раскладывается.

    ``kids_gender`` — «boys»/«girls» из ``integration_erp_cinsiyet`` детского товара.
    """
    key = superstep_subgroup_key(subgroup)
    key = SUPERSTEP_NAME_SUBGROUPS.get(key, key)
    if not key or key in SUPERSTEP_SKIPPED_SUBGROUPS:
        return ()
    route = SUPERSTEP_SUBGROUP_CATEGORIES.get(key, ())
    if isinstance(route, dict):
        kids_route = route.get(kids_gender) if gender == "kids" and kids_gender else None
        route = kids_route or route.get(gender) or route[""]
    return tuple(route)


# Разделы, куда подгруппа кладётся за неимением точного (корни и «Сумки и
# кошельки» для спортивных сумок): по плану §5.1 это видно в отчёте прогона.
SUPERSTEP_PARENT_PLACEMENTS = frozenset(
    {"shoes", "clothing", "underwear", "headwear", "accessories", "sports", "tableware", "bags-wallets"}
)


class SuperstepParser(AkinonParser):
    """Парсер superstep.com.tr по JSON Akinon (``?format=json``), без прокси."""

    SOURCE = "superstep"
    SOURCE_TITLE = "SuperStep"
    SITE_URL = "https://www.superstep.com.tr"
    DOMAIN = "superstep.com.tr"
    PARENT_PLACEMENTS = SUPERSTEP_PARENT_PLACEMENTS

    @classmethod
    def subgroup_route(
        cls, subgroup: Any, name: Any, brand: Any, gender: str, kids_gender: str = ""
    ) -> Tuple[str, Tuple[str, ...]]:
        """Подгруппа и маршрут по подгруппе сайта, названию и бренду — без запросов.

        Нужна и команде переноса уже загруженных товаров
        (``move_superstep_to_demand_categories``): раскладка та же, что при сборе.
        """
        name_subgroup = superstep_subgroup_from_name(name)
        if not subgroup:
            subgroup = name_subgroup
        elif {superstep_subgroup_key(subgroup), superstep_subgroup_key(name_subgroup)} == cls.HEADWEAR_SUBGROUPS:
            # Сайт путает «Bere» и «Şapka» (New Era Sun Shield — «Bere», а в
            # названии «… Çocuk Bej Şapka»): верим названию.
            subgroup = name_subgroup
        elif (
            superstep_subgroup_key(subgroup) in cls.LOOSE_TOP_SUBGROUPS
            and superstep_subgroup_key(name_subgroup) in cls.LOOSE_TOP_NAME_SUBGROUPS
        ):
            # В «Sweatshirt»/«Polar» сайт кладёт и флисовые куртки («Napapijri
            # … Polar Ceket»), и футболки («Nike Impossiblysoft … T-Shirt»); флис
            # («… Outdoor Polar») — во «Флиски», а не в «Толстовки».
            subgroup = name_subgroup
        route = resolve_superstep_category_slugs(subgroup, gender, kids_gender)
        key = superstep_subgroup_key(subgroup)
        name_words = set(superstep_subgroup_key(name).split())
        if key == "sapka":
            route = cls._cap_route(name, gender) or route
        elif key in {"bot", "bot & cizme"} and "ugg" in name_words | {superstep_subgroup_key(brand)}:
            # Ищут «угги», а не «сапоги UGG» (SEO-ядро 05.11).
            route = cls.UGG_ROUTE
        elif key == "terlik" and "clog" in name_words:
            # Crocs Classic Clog, Crocband Clog — сабо, а не шлёпанцы.
            route = cls.CLOG_ROUTE
        return subgroup, route

    UGG_ROUTE = ("ugg-boots", "boots", "shoes")
    CLOG_ROUTE = ("clogs", "sandals", "shoes")

    HEADWEAR_SUBGROUPS = frozenset({"sapka", "bere"})
    LOOSE_TOP_SUBGROUPS = frozenset({"sweatshirt", "polar", "hoodie"})
    LOOSE_TOP_NAME_SUBGROUPS = frozenset({"ceket", "mont", "yelek", "t-shirt", "polar"})

    # Тип кепки по названию («New Era … 940 Trucker … Şapka»): у сайта одна
    # подгруппа «Şapka» на все кепки и панамы. Детям — детские разделы.
    CAP_TYPES = (
        ("trucker", ("hw-trucker-caps", "hw-caps", "headwear"), ()),
        ("snapback", ("hw-snapbacks", "hw-caps", "headwear"), ()),
        ("bucket", ("hw-bucket-hats", "hw-summer-headwear", "headwear"),
         ("hw-childrens-panamas", "hw-children-headwear", "headwear")),
        ("balikci", ("hw-bucket-hats", "hw-summer-headwear", "headwear"),
         ("hw-childrens-panamas", "hw-children-headwear", "headwear")),
        ("visor", ("hw-visors", "hw-summer-headwear", "headwear"), ()),
        ("vizor", ("hw-visors", "hw-summer-headwear", "headwear"), ()),
    )

    @classmethod
    def _cap_route(cls, name: Any, gender: str) -> Tuple[str, ...]:
        words = set(superstep_subgroup_key(name).split())
        for marker, adult, kids in cls.CAP_TYPES:
            if marker in words:
                return kids if gender == "kids" else adult
        return ()
