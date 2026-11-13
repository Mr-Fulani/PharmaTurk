"""Парсер SuperStep на сохранённых ответах ``?format=json`` (04.11.2026).

Фрагменты настоящих ответов: длинные описания укорочены, у вариантов в
списках оставлены только поля, которые читает парсер.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from apps.catalog.models import Category
from apps.scrapers.models import ScrapedProductLog, ScraperConfig, ScrapingSession
from apps.scrapers.base.scraper import (
    CategoryPageNotFoundError,
    ScrapedProduct,
    ScraperAccessBlockedError,
    SiteCategoriesError,
)
from apps.catalog.utils.tr_vocab import translate_turkish_color
from apps.scrapers.parsers.superstep import (
    SuperstepFormatError,
    SuperstepParser,
    resolve_superstep_category_slugs,
    superstep_subgroup_from_name,
)
from apps.scrapers.services import ScraperIntegrationService

FIXTURES = Path(__file__).parent / "test_fixtures" / "superstep"
SITE = "https://www.superstep.com.tr"

PUMA_01 = "/urun/puma-palermo-leather-unisex-beyaz-spor-ayakkabi/396464-2/"
PUMA_03 = "/urun/puma-palermo-leather-unisex-siyah-spor-ayakkabi/396464/"
SAMBA = "/urun/adidas-samba-og-unisex-beyaz-spor-ayakkabi/b75806-1/"
NAUTICA_0HF = "/urun/nautica-erkek-gri-slim-fit-kisa-kollu-polo-yaka-t-shirt/k35052t-3/"
NAUTICA_4MY = "/urun/nautica-erkek-mavi-slim-fit-kisa-kollu-polo-yaka-t-shirt/k35052t-5/"
NAUTICA_1BW = "/urun/nautica-erkek-beyaz-slim-fit-kisa-kollu-polo-yaka-t-shirt/k35052t-1/"
MARKETPLACE = "/urun/adidas-samba-og-unisex-kahverengi-sneaker/34-ih9166-5/"

ROUTES = {
    PUMA_01: "card_puma_396464_01.json",
    PUMA_03: "card_puma_396464_03.json",
    SAMBA: "card_samba_B75806.json",
    NAUTICA_0HF: "card_nautica_K35052T_0HF.json",
    NAUTICA_4MY: "card_nautica_K35052T_4MY.json",
    NAUTICA_1BW: "card_nautica_K35052T_1BW.json",
    MARKETPLACE: "card_mp_34-IH9166.json",
    "/erkek-ayakkabi/": "list_erkek_ayakkabi.json",
    "/erkek-figur/": "list_erkek_figur.json",
    "/erkek/": "list_erkek_root.json",
}


def _fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def _parser(routes=None):
    """Парсер, который отвечает сохранёнными JSON и запоминает запросы."""
    parser = SuperstepParser()
    parser.requests = []
    table = dict(ROUTES, **(routes or {}))

    def fake_request(url, **kwargs):
        parsed = urlparse(url)
        assert parse_qs(parsed.query).get("format") == ["json"]
        parser.requests.append(parsed.path)
        body = table.get(parsed.path)
        return _fixture(body) if body and body.endswith(".json") else body

    parser._make_request = fake_request
    return parser


def _variants(product):
    return {v["sku"]: v for v in product.attributes["fashion_variants"]}


# --- карточка ----------------------------------------------------------------


def test_multicolor_model_collects_colors_inside_one_card():
    """Nautica K35052T: 4 цвета в одной модели; распроданный чужой цвет не открывается."""
    parser = _parser()

    product = parser.parse_product_detail(SITE + NAUTICA_0HF)

    assert parser.requests == [NAUTICA_0HF, NAUTICA_4MY, NAUTICA_1BW]  # 0TB распродан
    assert product.external_id == "superstep-K35052T"
    assert product.attributes["variant_group_id"] == "superstep-K35052T"
    variants = _variants(product)
    assert list(variants) == ["K35052T.0HF", "K35052T.4MY", "K35052T.1BW"]
    assert [v["sort_order"] for v in variants.values()] == [0, 1, 3]
    gray, blue, white = variants.values()
    assert (gray["color"], gray["price"], gray["old_price"], gray["is_available"]) == ("Gri", 749.7, 899.0, False)
    assert (blue["color"], blue["price"], blue["is_available"]) == ("Mavi", 999.6, True)
    assert white["external_id"] == "superstep-variant-K35052T.1BW"
    assert white["external_url"] == SITE + NAUTICA_1BW
    assert [s["size"] for s in white["sizes"]] == ["XS", "S", "M", "L", "XL", "XXL"]
    assert [s["is_available"] for s in white["sizes"]] == [True, True, False, False, False, False]
    # Внутренний код «1K35052T…» — не штрихкод производителя.
    assert {s["barcode"] for s in white["sizes"]} == {""}
    # Открытый цвет распродан — цена и ссылка товара от первого цвета в наличии.
    assert product.price == 999.6
    assert product.old_price == 1249.5  # как на сайте: −20 %, не retail_price 2 499
    assert product.url == SITE + NAUTICA_4MY
    assert product.is_available is True
    assert product.category == "polo-shirts"
    assert product.attributes["superstep_category_slugs"] == ["polo-shirts", "t-shirts", "tops", "clothing"]
    assert product.attributes["gender"] == "men"
    assert product.attributes["material"] == "%95 PAMUK %5 ELASTAN"
    assert product.brand == "Nautica"
    assert product.description.startswith("Nautica Erkek Gri Slim Fit")


def test_shoe_half_sizes_and_barcodes():
    parser = _parser()

    product = parser.parse_product_detail(SITE + SAMBA)

    assert parser.requests == [SAMBA]  # цвет «-»: модель одного цвета
    (variant,) = product.attributes["fashion_variants"]
    sizes = {row["size"]: row for row in variant["sizes"]}
    assert list(sizes) == ["36", "37", "39", "40", "40.5", "41", "42", "42.5", "43", "44", "45", "46", "46.5"]
    assert sizes["40.5"]["is_available"] is False
    assert sizes["42"]["is_available"] is True
    assert sizes["42"]["stock_quantity"] == SuperstepParser.DEFAULT_ASSUMED_STOCK_QUANTITY
    assert sizes["42"]["barcode"].isdigit() and len(sizes["42"]["barcode"]) == 13
    assert variant["color"] == "Beyaz"
    assert product.attributes["gender"] == "unisex"
    assert product.attributes["size_advice"] == "Yarım beden büyük almanı tavsiye ederiz."
    assert product.category == "sneakers"
    assert product.old_price is None  # previous_price 4 319 ниже цены — сайт не зачёркивает


def test_sizes_of_other_colors_are_not_mixed_in():
    """Akinon кладёт в размеры карточки и размеры, которые есть только у других цветов."""
    parser = _parser()

    product = parser.parse_product_detail(SITE + PUMA_01)

    assert parser.requests == [PUMA_01, PUMA_03]
    variants = _variants(product)
    assert list(variants) == ["396464.03", "396464.01"]
    white = variants["396464.01"]
    assert [s["size"] for s in white["sizes"]] == [
        "40", "41", "42", "42.5", "43", "44", "44.5", "45", "46", "47",
    ]
    assert white["external_url"] == SITE + PUMA_01
    assert len(white["images"]) == 7
    assert len(variants["396464.03"]["images"]) == 12
    # Главный — первый по порядку сайта цвет в наличии, с какого бы ни начали.
    assert product.url == SITE + PUMA_03
    assert product.sku == "396464"


@pytest.mark.parametrize(
    "prices,expected",
    [
        # Живые карточки 04.11.2026, зачёркнутая цена сверена на сайте.
        ({"price": "4194", "retail_price": "6990", "price_extra_field": {"previous_price": "5243.00"}}, 5243.0),
        ({"price": "4799", "retail_price": "5999", "price_extra_field": {"previous_price": "3599.00"}}, None),
        ({"price": "4899", "retail_price": "6999", "price_extra_field": {}}, 6999.0),
        ({"price": "7999", "retail_price": "7999"}, None),
    ],
)
def test_strikethrough_price_is_what_the_site_shows(prices, expected):
    assert SuperstepParser._selling_and_old_price(prices) == (float(prices["price"]), expected)


def test_marketplace_product_keeps_shop_price_and_basket_offer_for_manager():
    """34-IH9166: маркетплейс (mp_*), «SEPETTE %40 İNDİRİM» только в атрибутах."""
    parser = _parser()

    product = parser.parse_product_detail(SITE + MARKETPLACE)

    assert product.external_id == "superstep-34-IH9166"
    assert product.price == 7999.0
    assert product.old_price is None
    offers = [{"label": "SEPETTE %40 İNDİRİM", "basket_price": 4799.4}]
    assert product.attributes["superstep_basket_offers"] == offers
    (variant,) = product.attributes["fashion_variants"]
    assert variant["basket_offers"] == offers
    assert variant["color"] == "Kahverengi"
    assert [s["size"] for s in variant["sizes"]][:3] == ["36", "36.5", "37"]
    assert variant["sizes"][-1]["barcode"] == "4068805874857"
    assert product.brand == "adidas"
    assert product.description.startswith("Adımlarını kahve tonlarının")


def test_colors_grouped_by_mp_color_do_not_reopen_the_same_card():
    """Пилот 04.11: у бра Puma x Hyrox группа цветов — mp_color («SİYAH»),
    а integration_renk — «01»; карточка открывалась повторно как «другой цвет»."""
    url = "/urun/puma-x-hyrox-pwrmode-kadin-siyah-bra/265-529149/"
    parser = _parser({url: "card_mp_color_265-529149.json"})

    product = parser.parse_product_detail(SITE + url)

    assert parser.requests == [url]
    (variant,) = product.attributes["fashion_variants"]
    assert variant["color"] == "Siyah"  # капс «SİYAH» приводится к обычному виду
    assert [s["size"] for s in variant["sizes"]] == ["XS", "S", "M", "L"]
    assert product.category == "uw-sports-bras"


def test_numeric_sizes_sorted_by_value_not_by_akinon_order():
    """Детские New Balance: order 2850, 3500, 200180… — из разных систем."""
    url = "/urun/new-balance-9060-lifestyle-cocuk-siyah-spor-ayakkabi/pc9060bk-3/"
    parser = _parser({url: "card_kids_PC9060BK.json"})

    product = parser.parse_product_detail(SITE + url)

    (variant,) = product.attributes["fashion_variants"]
    assert [s["size"] for s in variant["sizes"]] == ["28.5", "30", "31", "32.5", "33.5", "35"]
    assert product.attributes["gender"] == "kids"


STANLEY = "/urun/stanley-the-iceflow-flip-straw-2-0-0-89l-unisex-beyaz-termos/13424/"
STANLEY_RED = "/urun/stanley-the-iceflow-flip-straw-2-0-0-89l-unisex-kirmizi-termos/13424/"


def _stanley_red_card():
    """Карточка красного цвета: тот же ответ с кодом цвета 0209 (как на сайте)."""
    card = json.loads(_fixture("card_stanley_13424.json"))
    attrs = card["product"]["attributes"]
    attrs["integration_renk"] = "0209"
    attrs["integration_model_renk"] = "13424.0209"
    attrs["integration_renk_detay"] = "Kırmızı"
    card["product"]["absolute_url"] = STANLEY_RED
    return json.dumps(card)


def test_color_of_type_without_variants_is_its_own_card():
    """Термос Stanley: у посуды нет модели вариантов цвета — соседние цвета
    не открываются (их фото не качаются), у цвета свой external_id."""
    parser = _parser({STANLEY: "card_stanley_13424.json"})

    product = parser.parse_product_detail(SITE + STANLEY)

    assert parser.requests == [STANLEY]
    assert product.external_id == "superstep-13424.0195"
    assert product.sku == "13424.0195"
    assert "fashion_variants" not in product.attributes
    assert product.attributes["superstep_color_ids"] == ["13424.0195"]
    assert product.attributes["color"] == "Beyaz"
    assert product.category == "thermoses"
    assert len(product.images) == 3


def test_listing_opens_each_color_of_type_without_variants_separately():
    tile = json.loads(_fixture("card_stanley_13424.json"))["product"]
    card = json.loads(_fixture("card_stanley_13424.json"))
    tile["extra_data"] = {"variants": card["variants"]}
    red = json.loads(_stanley_red_card())["product"]
    red["extra_data"] = {"variants": card["variants"]}
    listing = {"pagination": {"current_page": 1, "num_pages": 1}, "products": [tile, red]}
    parser = _parser({
        STANLEY: "card_stanley_13424.json",
        STANLEY_RED: _stanley_red_card(),
        "/termos/": json.dumps(listing),
    })
    parser.listing_guard = _Guard()

    products = list(parser.parse_product_list(SITE + "/termos/", max_pages=1))

    assert [p.external_id for p in products] == ["superstep-13424.0195", "superstep-13424.0209"]
    assert parser.requests == ["/termos/", STANLEY, STANLEY_RED]
    assert parser.listing_guard.attached == [("13424.0195", ("13424.0195",)), ("13424.0209", ("13424.0209",))]


def test_color_id_without_model_renk_uses_the_grouping_attribute():
    """Нет integration_model_renk — код цвета по атрибуту группы (mp_color)."""
    card = json.loads(_fixture("card_mp_color_265-529149.json"))
    card["product"]["attributes"].pop("integration_model_renk")

    assert SuperstepParser()._model_color_id(card["product"], card["variants"]) == "265-529149.SİYAH"


def test_kids_k_sizes_go_before_other_numeric_sizes():
    """adidas KI9437: «10K…13.5K», затем «1.5 2 2.5 28.5 33» (order у Akinon вперемешку)."""
    url = "/urun/adidas-campus-00s-cocuk-kahverengi-spor-ayakkabi/ki9437-1/"
    parser = _parser({url: "card_kids_KI9437.json"})

    (variant,) = parser.parse_product_detail(SITE + url).attributes["fashion_variants"]

    assert [s["size"] for s in variant["sizes"]] == [
        "10K", "11K", "11.5K", "12.5K", "13.5K", "1.5", "2", "2.5", "28.5", "33",
    ]


NIKE_GREEN = "/urun/nike-arswft-dfadv-crop-tank-kadin-yesil-t-shirt/265-fn2713-1/"


def test_color_without_subgroup_takes_it_from_another_color_of_the_model():
    """Nike 265-FN2713: у зелёного цвета нет integration_alt_grup, у белого — «Atlet»."""
    parser = _parser({NIKE_GREEN: "card_mp_no_subgroup_265-FN2713.json"})

    product = parser.parse_product_detail(SITE + NIKE_GREEN)

    assert product.attributes["superstep_subgroup"] == "Atlet"
    assert product.category == "tank-tops"
    assert product.attributes["gender"] == "women"


def test_subgroup_from_name_when_no_color_has_it():
    card = json.loads(_fixture("card_mp_no_subgroup_265-FN2713.json"))
    for group in card["variants"]:
        for option in group["options"]:
            (option["product"].get("attributes_kwargs") or {}).pop("integration_alt_grup", None)
    parser = _parser({NIKE_GREEN: json.dumps(card)})

    product = parser.parse_product_detail(SITE + NIKE_GREEN)

    assert product.attributes["superstep_subgroup"] == "T-Shirt"  # подпись из «… Kadın Yeşil T-Shirt»
    assert product.category == "t-shirts"


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Nike Arswft Dfadv Crop Tank Kadın Yeşil T-Shirt", "T-Shirt"),
        ("adidas Samba OG Unisex Kahverengi Sneaker", "Sneaker"),
        ("Puma Palermo Leather Unisex Beyaz Spor Ayakkabı", "Spor Ayakkabı"),
        ("Nautica Erkek Lacivert Deniz Şortu", "Deniz Şortu"),
        ("Eastpak Orbit Unisex Kırmızı Sırt Çantası", "Sırt Çantası"),
        ("Funko Pop Marvel Figür", "Figür"),
        ("Hediye Kartı 500 TL", ""),
    ],
)
def test_superstep_subgroup_from_name(name, expected):
    """Формат один — подпись, как у подгруппы сайта (``superstep_subgroup``)."""
    assert superstep_subgroup_from_name(name) == expected


@pytest.mark.parametrize(
    "erp_gender,expected",
    [
        ("BOYS", ("uw-boys-briefs", "uw-boys-underwear", "uw-children-underwear", "underwear")),
        ("GIRLS", ("uw-girls-panties", "uw-girls-underwear", "uw-children-underwear", "underwear")),
        ("CHILDREN", ("uw-children-underwear", "underwear")),
    ],
)
def test_kids_boxers_by_erp_gender(erp_gender, expected):
    """Детское бельё — по integration_erp_cinsiyet (BOYS/GIRLS), как в плане."""
    product = {
        "attributes": {"integration_cinsiyet": "Çocuk", "integration_erp_cinsiyet": erp_gender},
        "attributes_kwargs": {"integration_alt_grup": {"label": "Boxer"}},
    }

    assert SuperstepParser()._category_route(product) == ("Boxer", expected)


def test_unisex_backpack_goes_to_backpacks():
    """Рюкзаки Unisex — в «Рюкзаки» (SEO 05.11), а не в родительский раздел."""
    card = json.loads(_fixture("card_stanley_13424.json"))
    card["product"]["attributes_kwargs"]["integration_alt_grup"] = {"label": "Sırt Çantası"}
    parser = _parser({STANLEY: json.dumps(card)})

    product = parser.parse_product_detail(SITE + STANLEY)

    assert product.category == "backpacks"
    assert parser._unmapped_report() == ""


def test_sports_bag_in_parent_section_is_reported():
    """Спортивные сумки — в «Сумки и кошельки» (точного раздела нет): видно в отчёте прогона."""
    card = json.loads(_fixture("card_stanley_13424.json"))
    card["product"]["attributes_kwargs"]["integration_alt_grup"] = {"label": "Spor Çantası"}
    parser = _parser({STANLEY: json.dumps(card)})

    product = parser.parse_product_detail(SITE + STANLEY)

    assert product.category == "bags-wallets"
    assert parser._unmapped_report() == (
        "В родительском разделе (точного нет): 1 товаров — Spor Çantası → bags-wallets 1."
    )


PUMA_399025_01 = "/urun/puma-easy-rider-mix-unisex-beyaz-spor-ayakkabi/399025-3/"
PUMA_399025_06 = "/urun/puma-easy-rider-mix-unisex-beyaz-haki-spor-ayakkabi/399025-6/"


def test_same_color_names_inside_model_get_the_maker_colorway():
    """Puma 399025: два цвета «Beyaz» различаются расцветкой производителя;
    перевод цвета различитель сохраняет."""
    parser = _parser({PUMA_399025_01: "card_puma_399025_01.json", PUMA_399025_06: "card_puma_399025_06.json"})

    product = parser.parse_product_detail(SITE + PUMA_399025_01)

    colors = [v["color"] for v in product.attributes["fashion_variants"]]
    # Турецкое «BEYAZ» из расцветки «BEYAZ-Velvet Moss» убрано: на витрине и в фиде ВК его быть не должно.
    assert colors == ["Beyaz · Velvet Moss", "Beyaz · White-Black"]
    assert translate_turkish_color(colors[0], "ru") == "Белый · Velvet Moss"
    assert product.attributes["fashion_variants"][1]["display_name"].endswith("- Beyaz · White-Black")


def test_color_detail_does_not_depend_on_sibling_stock():
    """Соседний «Beyaz» распродан и не открывается — уточнение остаётся тем же."""
    card = json.loads(_fixture("card_puma_399025_01.json"))
    for group in card["variants"]:
        for option in group["options"]:
            option["in_stock"] = False
    parser = _parser({PUMA_399025_01: json.dumps(card)})

    product = parser.parse_product_detail(SITE + PUMA_399025_01)

    assert parser.requests == [PUMA_399025_01]
    assert [v["color"] for v in product.attributes["fashion_variants"]] == ["Beyaz · White-Black"]


def test_color_detail_from_opened_cards_when_variants_have_no_color_names():
    """У вариантов маркетплейса (mp_*) в карточке нет названий цветов —
    одинаковые цвета находятся по карточкам открытых цветов."""
    cards = {}
    for path, name in ((PUMA_399025_01, "card_puma_399025_01.json"), (PUMA_399025_06, "card_puma_399025_06.json")):
        card = json.loads(_fixture(name))
        for group in card["variants"]:
            for option in group["options"]:
                attrs = option["product"]["attributes"]
                for key in ("integration_renk_detay", "integration_hos_renk_detay", "integration_renk_tonu",
                            "integration_erp_renk_aciklama"):
                    attrs.pop(key, None)
        cards[path] = json.dumps(card)
    parser = _parser(cards)

    product = parser.parse_product_detail(SITE + PUMA_399025_01)

    assert [v["color"] for v in product.attributes["fashion_variants"]] == [
        "Beyaz · Velvet Moss", "Beyaz · White-Black",
    ]


@pytest.mark.parametrize(
    "colorway,expected",
    [
        ("BEYAZ-Velvet Moss", "Velvet Moss"),
        ("PUMA White-PUMA Black", "PUMA White-PUMA Black"),
        ("Beyaz-Kahverengi", ""),
        ("CHESTNUT (KAHVE)", "CHESTNUT"),
        ("TOZLU KAKAO", ""),  # турецкие слова вне словаря цветов — не берём
        ("LIGHT BRONZE", "LIGHT BRONZE"),
        ("KOYU GRI-Black", "Black"),  # турецкий модификатор «koyu» латиницей тоже убирается
        ("AÇIK MAVİ/White", "White"),
        ("INDIGO-White", "INDIGO-White"),  # английский цвет из словаря не теряется
        ("Light Kakao", ""),  # оттенок без английского цвета — «Kakao» турецкое
        ("Light Grey", "Light Grey"),
        ("Kum Rengi-Sand", "Sand"),  # «rengi», «tonu» и др. — турецкие модификаторы
        ("Gri Tonu/Black", "Black"),
        ("Siyah/Gümüş", ""),  # Anta: расцветка по-турецки — тогда код цвета
    ],
)
def test_colorway_without_turkish_color_words(colorway, expected):
    assert SuperstepParser._colorway({"attributes": {"integration_erp_renk_aciklama": colorway}}) == expected


def test_same_color_names_without_colorway_get_the_color_code():
    cards = {}
    for path, name in ((PUMA_399025_01, "card_puma_399025_01.json"), (PUMA_399025_06, "card_puma_399025_06.json")):
        card = json.loads(_fixture(name))
        card["product"]["attributes"].pop("integration_erp_renk_aciklama", None)
        for group in card["variants"]:
            for option in group["options"]:
                option["product"]["attributes"].pop("integration_erp_renk_aciklama", None)
        cards[path] = json.dumps(card)
    parser = _parser(cards)

    product = parser.parse_product_detail(SITE + PUMA_399025_01)

    assert [v["color"] for v in product.attributes["fashion_variants"]] == ["Beyaz · 06", "Beyaz · 01"]


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Без турецкой замены I→ı: было бы «Nıke», «Tımberland» (slug «tmberland»).
        ("NIKE", "Nike"),
        ("TIMBERLAND", "Timberland"),
        ("LEVI'S", "Levi's"),
        ("STANLEY", "Stanley"),
        ("NEW BALANCE", "New Balance"),
        # Аббревиатуры не трогаем.
        ("KİNETİX", "Kinetix"),  # İ → I, без комбинируемой точки
        ("ASICS", "ASICS"),
        ("DKNY", "DKNY"),
        ("UGG", "UGG"),
        ("EA7", "EA7"),
        ("adidas", "adidas"),
    ],
)
def test_brand_in_caps_is_normalized(raw, expected):
    product = {"attributes_kwargs": {"integration_alt_marka": {"label": raw}}}

    assert SuperstepParser()._brand(product) == expected


NEW_ERA_TRUCKER = "/urun/new-era-midi-homefield-940-trucker-unisex-mavi-sapka/60856247/"
NEW_ERA_SUN_SHIELD = "/urun/new-era-mlb-league-essentials-new-york-yankees-sun-shield-cocuk-bej-sapka/60667522/"
NIKE_RENKLI = "/urun/nike-ultra-comfort-erkek-renkli-boxer/0000ke1257-1/"
LACOSTE_KIDS = "/urun/lacoste-cocuk-bisiklet-yaka-mavi-t-shirt/tj7365/"


@pytest.mark.parametrize(
    "subgroup,name,expected",
    [
        # Волна 2 на проде 05.11: у сайта подгруппа «Sweatshirt», а товар — куртка или футболка.
        ("Sweatshirt", "Napapijri Yupik 3 Erkek Krem Polar Ceket", "jackets"),
        ("Sweatshirt", "Nike Impossiblysoft Kadın Beyaz T-Shirt", "t-shirts"),
        ("Polar", "The North Face Glacier Erkek Siyah Yelek", "vests"),
        # SEO 05.11: флис — «Флиски», свитшоты — «Толстовки и худи».
        ("Sweatshirt", "The North Face Crest Fz Erkek Gri Outdoor Polar", "fleece"),
        ("Polar", "Columbia Fast Trek Kadın Siyah Polar", "fleece"),
        ("Sweatshirt", "adidas Lk Dy Çocuk Turuncu Sweatshirt", "hoodies"),
        # Поло с «… Polo Yaka T-Shirt» в названии остаются поло.
        ("Polo", "Nautica Erkek Gri Slim Fit Kısa Kollu Polo Yaka T-Shirt", "polo-shirts"),
    ],
)
def test_loose_top_subgroup_is_refined_by_name(subgroup, name, expected):
    product = {
        "name": name,
        "attributes": {"integration_cinsiyet": "Erkek"},
        "attributes_kwargs": {"integration_alt_grup": {"label": subgroup}},
    }

    assert SuperstepParser()._category_route(product)[1][0] == expected


@pytest.mark.parametrize(
    "subgroup,name,brand,expected",
    [
        # SEO 05.11: ищут «угги» и «сабо» — у моделей свои разделы внутри подгруппы сайта.
        ("Bot", "UGG Classic Mini II Kadın Kahverengi Bot", "UGG", ("ugg-boots", "boots", "shoes")),
        ("Bot & Çizme", "UGG Classic Tall II Kadın Siyah Çizme", "UGG", ("ugg-boots", "boots", "shoes")),
        ("Bot", "Timberland Premium 6 Inch Erkek Sarı Bot", "TIMBERLAND", ("boots", "shoes")),
        ("Terlik", "Crocs Classic Clog Unisex Siyah Terlik", "CROCS", ("clogs", "sandals", "shoes")),
        ("Terlik", "Crocs Classic Slide Unisex Siyah Terlik", "CROCS", ("slides", "sandals", "shoes")),
    ],
)
def test_ugg_and_clog_models_get_own_sections(subgroup, name, brand, expected):
    product = {
        "name": name,
        "attributes": {"integration_cinsiyet": "Kadın"},
        "attributes_kwargs": {
            "integration_alt_grup": {"label": subgroup},
            "integration_alt_marka": {"label": brand},
        },
    }

    assert SuperstepParser()._category_route(product)[1] == expected
    assert set(expected) <= _catalog_slugs()


def test_trucker_cap_goes_to_trucker_caps():
    """У сайта одна подгруппа «Şapka» на все кепки; тип — по названию."""
    parser = _parser({NEW_ERA_TRUCKER: "card_newera_trucker_60856247.json"})

    assert parser.parse_product_detail(SITE + NEW_ERA_TRUCKER).category == "hw-trucker-caps"


def test_cap_with_beanie_subgroup_is_a_kids_cap_by_name():
    """New Era Sun Shield: подгруппа сайта «Bere», в названии «… Çocuk Bej Şapka»."""
    parser = _parser({NEW_ERA_SUN_SHIELD: "card_newera_sunshield_kids_60667522.json"})

    product = parser.parse_product_detail(SITE + NEW_ERA_SUN_SHIELD)

    assert product.attributes["superstep_subgroup"] == "Şapka"
    assert product.category == "hw-childrens-caps"


@pytest.mark.parametrize(
    "name,gender,expected",
    [
        ("New Era 9Forty Snapback Unisex Siyah Şapka", "unisex", "hw-snapbacks"),
        ("Kangol Bucket Kadın Bej Şapka", "women", "hw-bucket-hats"),
        ("Kangol Bucket Çocuk Bej Şapka", "kids", "hw-childrens-panamas"),
        ("New Era 9Forty Unisex Siyah Şapka", "unisex", ""),
    ],
)
def test_cap_type_by_name(name, gender, expected):
    route = SuperstepParser._cap_route(name, gender)
    assert (route[0] if route else "") == expected


def test_renkli_color_is_translated_and_duplicates_get_a_code():
    """Nike 0000KE1257: два цвета «RENKLİ» (WZS, 425) с одинаковой расцветкой «MULTI»."""
    parser = _parser({NIKE_RENKLI: "card_nike_renkli_0000KE1257.json"})

    product = parser.parse_product_detail(SITE + NIKE_RENKLI)

    colors = [v["color"] for v in product.attributes["fashion_variants"]]
    assert colors == ["Renkli · WZS"]
    assert translate_turkish_color(colors[0], "ru") == "Разноцветный · WZS"
    # Название модели без цвета варианта («Renkli»): у модели три цвета.
    assert product.name == "Nike Ultra Comfort Erkek Boxer"


def test_model_name_has_no_color_of_the_opened_variant():
    """Иначе белый цвет Nautica в Списке заявки: «Nautica Erkek Gri … — Белый»."""
    parser = _parser()

    nautica = parser.parse_product_detail(SITE + NAUTICA_0HF)
    samba = parser.parse_product_detail(SITE + SAMBA)

    assert nautica.name == "Nautica Erkek Slim Fit Kısa Kollu Polo Yaka T-Shirt"
    assert samba.name == "adidas Samba OG Unisex Beyaz Spor Ayakkabı"  # модель одного цвета


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Puma Easy Rider Mix Unisex Beyaz Haki Spor Ayakkabı", "Puma Easy Rider Mix Unisex Spor Ayakkabı"),
        ("Nike Dunk Low Retro Erkek Beyaz/Gri Sneaker", "Nike Dunk Low Retro Erkek Sneaker"),
        ("Converse Çocuk Açık Mavi Sneaker", "Converse Çocuk Sneaker"),
        ("Nike Club Erkek Baskılı Siyah Sweatshirt", "Nike Club Erkek Baskılı Sweatshirt"),
        ("Nike Everyday Unisex Çok Renkli Çorap", "Nike Everyday Unisex Çorap"),  # не «Çok Çorap»
        ("Converse Chuck 70 Unisex Kum Rengi Sneaker", "Converse Chuck 70 Unisex Sneaker"),
        ("Nike Erkek Kamuflaj Desenli Şort", "Nike Erkek Kamuflaj Desenli Şort"),  # узор, не цвет
    ],
)
def test_model_name_without_color_words(name, expected):
    assert SuperstepParser._model_name({"name": name}, 2, name.split()[0]) == expected


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Mavi Erkek Mavi Jean", "Mavi Erkek Jean"),  # бренд в начале остаётся, цвет — нет
        ("Erkek Mavi Jean", "Erkek Mavi Jean"),  # не с бренда — слово бренда не трогаем
    ],
)
def test_model_name_keeps_brand_equal_to_color(name, expected):
    assert SuperstepParser._model_name({"name": name}, 2, "Mavi") == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("13-14 Yaş", "13-14 лет"),
        ("2 Yaş", "2 года"),
        ("1-2 Yaş", "1-2 года"),
        ("1 Yaş", "1 год"),
        ("11-12 Yaş", "11-12 лет"),
        ("18-24 Ay", "18-24 мес."),
        ("6 Ay", "6 мес."),
        ("42,5", "42.5"),
    ],
)
def test_age_sizes_in_russian(raw, expected):
    assert SuperstepParser._normalize_size(raw) == expected


def test_age_sizes_sorted_by_age():
    labels = ["13-14 Yaş", "2 Yaş", "18-24 Ay", "6 Yaş", "6 Ay"]
    options = [{"label": label} for label in labels]

    ordered = sorted(range(len(options)), key=lambda i: SuperstepParser._size_sort_key(options[i], i))

    assert [SuperstepParser._normalize_size(labels[i]) for i in ordered] == [
        "6 мес.", "18-24 мес.", "2 года", "6 лет", "13-14 лет",
    ]


def test_kids_age_sizes_from_live_card():
    """Lacoste TJ7365: «6 Yaş, 10 Yaş, 12 Yaş, 14 Yaş, 8 Yaş» шли не по порядку."""
    parser = _parser({LACOSTE_KIDS: "card_lacoste_kids_yas_TJ7365.json"})

    (variant, *_) = parser.parse_product_detail(SITE + LACOSTE_KIDS).attributes["fashion_variants"]
    sizes = [s["size"] for s in variant["sizes"]]

    assert sizes == sorted(sizes, key=lambda size: int(size.split()[0]))
    assert all(size.endswith(("лет", "года", "год")) for size in sizes)


def test_colorway_without_model_name_words():
    """Palermo: «Palermo Lth PUMA White-Vapor Gray-Gum» → без названия модели."""
    colorway = SuperstepParser._colorway(
        {"attributes": {"integration_erp_renk_aciklama": "Palermo Lth PUMA White-Vapor Gray-Gum"}},
        {"palermo", "lth", "puma", "leather", "unisex"},
    )

    assert colorway == "White-Vapor Gray-Gum"


def test_unmapped_subgroup_is_not_loaded():
    figur = json.loads(_fixture("list_erkek_figur.json"))["products"][0]
    card = {"product": figur, "variants": figur["extra_data"]["variants"]}
    parser = _parser({"/urun/figur/1/": json.dumps(card)})

    assert parser.parse_product_detail(SITE + "/urun/figur/1/") is None
    assert parser.unmapped == {"Figür": 1}


def test_removed_product_is_skipped():
    assert _parser().parse_product_detail(SITE + "/urun/yok/x/") is None


def test_card_without_variants_is_a_format_error():
    parser = _parser({"/urun/bozuk/x/": json.dumps({"product": {"name": "x"}})})

    with pytest.raises(SuperstepFormatError):
        parser.parse_product_detail(SITE + "/urun/bozuk/x/")


def test_html_instead_of_json_stops_as_blocked():
    parser = _parser({"/urun/waf/x/": "<html><title>Access denied</title></html>"})

    with pytest.raises(ScraperAccessBlockedError):
        parser.parse_product_detail(SITE + "/urun/waf/x/")


# --- раскладка ----------------------------------------------------------------


@pytest.mark.parametrize(
    "subgroup,gender,expected",
    [
        ("Spor Ayakkabı & Sneaker", "men", ("sneakers", "shoes")),
        ("İç Giyim", "women", ("uw-womens-underwear", "underwear")),
        ("İç Giyim", "unisex", ("underwear",)),
        ("Sırt Çantası", "women", ("acc-womens-backpacks", "womens-bags", "bags-wallets", "accessories")),
        ("Sırt Çantası", "kids", ("backpacks", "bags-wallets", "accessories")),
        ("Sırt Çantası", "", ("backpacks", "bags-wallets", "accessories")),
        ("Süluk", "", ("thermoses", "drinkware", "tableware")),
        ("Şapka", "", ("hw-baseball-caps", "hw-caps", "headwear")),
        ("Termos", "", ("thermoses", "drinkware", "tableware")),
        # Детям — детские разделы (пилот 04.11: кепки и бельё шли во взрослые).
        ("Şapka", "kids", ("hw-childrens-caps", "hw-children-headwear", "headwear")),
        ("Bere", "kids", ("hw-childrens-beanies", "hw-children-headwear", "headwear")),
        ("İç Giyim", "kids", ("uw-children-underwear", "underwear")),
        ("Bra & Spor Sütyeni", "kids", ("uw-girls-underwear", "uw-children-underwear", "underwear")),
        ("Boxer", "men", ("uw-boxers", "uw-mens-underwear", "underwear")),
        ("Boxer", "kids", ("uw-children-underwear", "underwear")),
        # Подгруппа подписью из названия («Sneaker») раскладывается как подгруппа сайта.
        ("Sneaker", "men", ("sneakers", "shoes")),
        ("Figür", "men", ()),
        ("Satranç Takımı", "", ()),
        ("281", "", ()),
        ("Hediye Kartı", "", ()),
    ],
)
def test_subgroup_routes(subgroup, gender, expected):
    assert resolve_superstep_category_slugs(subgroup, gender) == expected


def _catalog_slugs():
    """Все slug дерева категорий каталога (как его создаёт seed_catalog_data)."""
    from apps.catalog import constants

    slugs = {row[0] for row in constants.ROOT_CATEGORIES}

    def walk(rows):
        for row in rows:
            slugs.add(row[2])
            if len(row) > 5 and isinstance(row[5], (list, tuple)):
                walk(row[5])

    for name in dir(constants):
        if name.endswith("_SUBCATEGORIES") and isinstance(getattr(constants, name), list):
            walk(getattr(constants, name))
    return slugs


def test_every_route_slug_exists_in_catalog_tree():
    """Опечатка в slug молча увела бы товары в родительский раздел."""
    from apps.scrapers.parsers.superstep import SUPERSTEP_SUBGROUP_CATEGORIES

    known = _catalog_slugs()
    routes = []
    for route in SUPERSTEP_SUBGROUP_CATEGORIES.values():
        routes.extend(route.values() if isinstance(route, dict) else [route])
    missing = {slug for route in routes for slug in route if slug not in known}

    assert missing == set()


@pytest.mark.django_db
def test_service_takes_most_specific_existing_category_over_root_task():
    clothing = Category.objects.create(name="Одежда", slug="clothing")
    tops = Category.objects.create(name="Верх", slug="tops", parent=clothing)
    Category.objects.create(name="Футболки", slug="t-shirts", parent=tops)
    shoes = Category.objects.create(name="Обувь", slug="shoes")
    product = ScrapedProduct(
        name="Nautica Polo",
        category="polo-shirts",
        source="superstep",
        attributes={"superstep_category_slugs": ["polo-shirts", "t-shirts", "tops", "clothing"]},
    )
    # Задача на корень «Обувь» (или категория по умолчанию) раскладку не перебивает.
    session = SimpleNamespace(target_category=shoes, scraper_config=SimpleNamespace(default_category=shoes))

    ScraperIntegrationService()._apply_category_mapping(session, product)

    assert product.category == "t-shirts"  # «Поло» в каталоге нет — ближайший родитель
    assert product._category_override.slug == "t-shirts"


def _tracksuit(route=("tracksuits", "suits", "clothing")):
    return ScrapedProduct(
        name="Nike Club Erkek Eşofman Takımı",
        category=route[0],
        source="superstep",
        attributes={"superstep_category_slugs": list(route)},
    )


@pytest.mark.django_db
def test_clothing_route_never_lands_in_sports_section():
    """Решение владельца 11.11.2026: спорттовары — снаряды и предметы, не одежда. Раздел
    ``tracksuits`` лежал под «Спорттоварами», и костюмы сохранялись спорттоварами."""
    sports = Category.objects.create(name="Спорттовары", slug="sports")
    sportswear = Category.objects.create(name="Спортивная одежда и обувь", slug="sportswear-footwear", parent=sports)
    tracksuits = Category.objects.create(name="Спортивные костюмы", slug="tracksuits", parent=sportswear)
    clothing = Category.objects.create(name="Одежда", slug="clothing")
    suits = Category.objects.create(name="Костюмы", slug="suits", parent=clothing)
    session = SimpleNamespace(target_category=None, scraper_config=SimpleNamespace(default_category=None))
    service = ScraperIntegrationService()

    product = _tracksuit()
    service._apply_category_mapping(session, product)
    assert product._category_override == suits

    # Раздел перенесли в одежду — костюмы идут в него.
    Category.objects.filter(pk=tracksuits.pk).update(parent=suits)
    product = _tracksuit()
    service._apply_category_mapping(session, product)
    assert product._category_override == tracksuits

    # Снаряд остаётся спорттоваром.
    balls = Category.objects.create(name="Мячи", slug="basketball-balls", parent=sports)
    ball = _tracksuit(("basketball-balls", "basketball", "team-sports", "sports"))
    service._apply_category_mapping(session, ball)
    assert ball._category_override == balls


def test_only_equipment_subgroups_route_to_sports():
    """В «Спорттовары» ведут только подгруппы снарядов и предметов: новая строка таблицы
    с одеждой или обувью под корнем ``sports`` — ошибка."""
    from apps.scrapers.parsers.superstep import SUPERSTEP_SUBGROUP_CATEGORIES

    to_sports = {
        key for key, route in SUPERSTEP_SUBGROUP_CATEGORIES.items()
        for variant in (route.values() if isinstance(route, dict) else [route]) if variant[-1] == "sports"
    }

    assert to_sports == {
        "basketbol topu", "dizlik", "kolluk", "tekmelik", "yuzucu gozlugu", "yuzme aksesuari",
        "spor aksesuarlari", "antrenman aksesuari", "havlu",
    }


def test_route_slugs_are_not_shared_between_catalog_roots():
    """Slug маршрута, объявленный в дереве двух корней, достаётся тому, кого сидер создал
    последним. ``tracksuits`` (одежда и спорттовары) до 13.11.2026 так попадал в «Спорттовары»;
    дубль убран, проверка типа в ``route_categories`` осталась страховкой."""
    import ast
    from pathlib import Path

    from apps.catalog import constants
    from apps.scrapers.parsers.superstep import SUPERSTEP_SUBGROUP_CATEGORIES

    declared = {}

    def walk(node, tree_name):
        if isinstance(node, (ast.List, ast.Tuple)):
            head = node.elts[:5]
            if len(head) == 5 and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in head):
                declared.setdefault(head[2].value, set()).add(tree_name)
            for element in node.elts:
                walk(element, tree_name)

    for statement in ast.parse(Path(constants.__file__).read_text(encoding="utf-8")).body:
        if isinstance(statement, ast.Assign) and getattr(statement.targets[0], "id", "").endswith("_SUBCATEGORIES"):
            walk(statement.value, statement.targets[0].id)
    route_slugs = {
        slug for route in SUPERSTEP_SUBGROUP_CATEGORIES.values()
        for variant in (route.values() if isinstance(route, dict) else [route]) for slug in variant
    }

    assert {slug for slug in route_slugs if len(declared.get(slug, ())) > 1} == set()


@pytest.mark.django_db
def test_product_without_catalog_section_is_not_loaded():
    """Нет ни одного раздела маршрута — товар не уходит в раздел задачи или
    «по умолчанию», а пропускается с причиной «Не разложено»."""
    shoes = Category.objects.create(name="Обувь", slug="shoes")
    config = ScraperConfig.objects.create(
        name="superstep-test", parser_class="superstep", base_url=SITE, default_category=shoes,
    )
    session = ScrapingSession.objects.create(scraper_config=config, status="running", start_url=SITE)
    product = ScrapedProduct(
        name="Stanley Termos",
        url=SITE + STANLEY,
        external_id="superstep-13424.0195",
        source="superstep",
        images=["https://8f08a8-ss.akinoncloudcdn.com/products/x.jpg"],
        attributes={"superstep_subgroup": "Termos", "superstep_category_slugs": ["drinkware", "tableware"]},
    )
    service = ScraperIntegrationService()
    service._normalize_scraped_media = lambda *args, **kwargs: pytest.fail("фото не качаются")
    service._process_single_product = lambda *args, **kwargs: pytest.fail("товар не сохраняется")

    results = service._process_scraped_products(session, [product])

    assert results["skipped"] == 1 and results["created"] == 0
    log = ScrapedProductLog.objects.get(session=session)
    assert log.action == "skipped"
    assert "Не разложено" in log.message and "Termos" in log.message


@pytest.mark.django_db
def test_explicit_subcategory_in_task_wins():
    clothing = Category.objects.create(name="Одежда", slug="clothing")
    tshirts = Category.objects.create(name="Футболки", slug="t-shirts", parent=clothing)
    product = ScrapedProduct(
        name="Polo",
        source="superstep",
        attributes={"superstep_category_slugs": ["polo-shirts", "clothing"]},
    )
    session = SimpleNamespace(target_category=tshirts, scraper_config=SimpleNamespace(default_category=None))

    ScraperIntegrationService()._apply_category_mapping(session, product)

    assert product.category == "t-shirts"


# --- обход раздела -------------------------------------------------------------


class _Guard:
    """ListingGuard без базы: запоминает решения и отпечатки."""

    def __init__(self, known=None):
        self.known = dict(known or {})
        self.attached = []
        self.covered = []

    def prefetch(self, identities):
        pass

    def should_open(self, identity, fingerprint):
        return self.known.get(identity) != fingerprint

    def attach(self, product, identity, fingerprint, *, covers=()):
        self.attached.append((identity, tuple(covers)))
        for covered in covers:
            self.known[covered] = fingerprint

    def remember_covered(self, identity, fingerprint):
        self.covered.append(identity)


def test_listing_opens_each_model_once_and_skips_unchanged_rows():
    parser = _parser()
    parser.listing_guard = _Guard()

    products = list(parser.parse_product_list(SITE + "/erkek-ayakkabi/", max_pages=1))

    # Строка 392982 — карточка снята (404): пропущена, обход идёт дальше.
    assert [p.external_id for p in products] == ["superstep-B75806", "superstep-396464"]
    # Второй цвет Puma уже загружен вместе с моделью — карточка не открывалась.
    assert parser.requests.count(PUMA_03) == 1
    assert parser.listing_guard.covered == ["396464.03"]
    assert parser.listing_guard.attached[1] == ("396464.01", ("396464.03", "396464.01"))
    assert parser.has_more_pages is True and parser.next_start_page == 2

    # Второй обход: строки не изменились — ни одной карточки.
    known = {}
    for tile in json.loads(_fixture("list_erkek_ayakkabi.json"))["products"]:
        known[parser._model_color_id(tile)] = parser._tile_fingerprint(tile)
    again = _parser()
    again.listing_guard = _Guard(known)

    assert list(again.parse_product_list(SITE + "/erkek-ayakkabi/", max_pages=1)) == []
    assert again.requests == ["/erkek-ayakkabi/"]


def test_fingerprint_changes_with_price_and_stock():
    tile = json.loads(_fixture("list_erkek_ayakkabi.json"))["products"][0]
    parser = SuperstepParser()
    base = parser._tile_fingerprint(tile)

    cheaper = json.loads(json.dumps(tile))
    cheaper["price"] = "6999"
    sold_out = json.loads(json.dumps(tile))
    sold_out["extra_data"]["variants"][1]["options"][0]["in_stock"] = False
    other_stock_count = json.loads(json.dumps(tile))
    other_stock_count["stock"] = 1

    assert parser._tile_fingerprint(cheaper) != base
    assert parser._tile_fingerprint(sold_out) != base
    assert parser._tile_fingerprint(other_stock_count) == base  # точный остаток не храним


def test_unmapped_rows_are_reported_and_do_not_stall_the_category():
    parser = _parser()

    assert list(parser.parse_product_list(SITE + "/erkek-figur/", max_pages=1)) == []

    assert parser.requests == ["/erkek-figur/"]  # карточки фигурок не открывались
    assert "Не разложено (не загружены): 2 строк — Figür 2." in parser.stop_reason
    assert parser.catalog_state._get("progress", "last") == (1, 0)


def test_missing_category_page_is_not_found():
    with pytest.raises(CategoryPageNotFoundError):
        list(_parser().parse_product_list(SITE + "/yok/", max_pages=1))


def test_listing_without_products_is_a_format_error():
    parser = _parser({"/bozuk/": json.dumps({"pagination": {}})})

    with pytest.raises(SuperstepFormatError):
        list(parser.parse_product_list(SITE + "/bozuk/", max_pages=1))


# --- разделы сайта и ссылки ----------------------------------------------------


def test_site_categories_are_catalog_roots():
    categories = _parser().parse_categories()

    assert [(row["name"], row["url"], row["external_id"]) for row in categories] == [
        ("KADIN", SITE + "/kadin/", "2"),
        ("ERKEK", SITE + "/erkek/", "31"),
        ("ÇOCUK", SITE + "/cocuk/", "121"),
        ("HEARTBEAT", SITE + "/heartbeat-1/", "1125"),
    ]
    for row in categories:
        assert SuperstepParser.is_category_url(row["url"])
        assert row["source"] == "superstep"


def test_site_categories_fail_without_category_filter():
    parser = _parser({"/erkek/": json.dumps({"facets": [], "products": []})})

    with pytest.raises(SiteCategoriesError):
        parser.parse_categories()


@pytest.mark.parametrize(
    "url,is_product",
    [
        (SITE + SAMBA, True),
        (SITE + "/product/724429/", True),
        (SITE + "/erkek-spor-ayakkabi/", False),
        (SITE + "/erkek-spor-ayakkabi/?page=3", False),
    ],
)
def test_url_kinds(url, is_product):
    assert SuperstepParser.is_product_url(url) is is_product
    assert SuperstepParser.is_category_url(url) is not is_product
    assert SuperstepParser.supports_page_chunking_for_url(url) is not is_product


def test_home_and_other_sites_are_not_categories():
    assert not SuperstepParser.is_category_url(SITE + "/")
    assert not SuperstepParser.is_category_url("https://www.flo.com.tr/sandalet")
