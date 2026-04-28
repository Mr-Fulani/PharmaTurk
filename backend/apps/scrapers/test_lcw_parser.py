from apps.scrapers.parsers.lcw import LcwParser


LCW_CATEGORY_HTML = """
<html>
  <body>
    <h1>ERKEK TISORT</h1>
    <a href="/100-pamuk-regular-fit-basic-tisort-siyah-o-4827603">
      LCWAIKIKI Classic %100 Pamuk Regular Fit Basic Tisort 299,99 TL +54
    </a>
    <a href="/soft-touch-tisort-saks-o-4827604">
      LCW Vision Loose Fit Basic Soft Touch Tisort 499,99 TL +12
    </a>
    <a href="/100-pamuk-regular-fit-basic-tisort-siyah-o-4827603">
      duplicate
    </a>
  </body>
</html>
"""


LCW_CATEGORY_WITH_SAME_FAMILY_VARIANTS_HTML = """
<html>
  <body>
    <h1>ERKEK TISORT</h1>
    <a href="/100-pamuk-regular-fit-basic-tisort-siyah-o-4827603">
      LCWAIKIKI Classic %100 Pamuk Regular Fit Basic Tisort 299,99 TL +54
    </a>
    <a href="/100-pamuk-regular-fit-basic-tisort-beyaz-o-4869998">
      LCWAIKIKI Classic %100 Pamuk Regular Fit Basic Tisort 299,99 TL +54
    </a>
    <a href="/soft-touch-tisort-saks-o-4827604">
      LCW Vision Loose Fit Basic Soft Touch Tisort 499,99 TL +12
    </a>
  </body>
</html>
"""


LCW_DETAIL_HTML = """
<html>
  <head>
    <title>LCWAIKIKI Classic Siyah %100 Pamuk Regular Fit Basic Tişört - S60418Z8-CVL | LCW</title>
    <meta property="og:title" content="LCWAIKIKI Classic Siyah %100 Pamuk Regular Fit Basic Tişört - S60418Z8-CVL | LCW" />
    <meta property="og:image" content="https://img-lcwaikiki.mncdn.com/mnpadding/320/426/ffffff/pim/productimages/20261/8355849/v1/l_20261-s60418z8-cvl_a.jpg" />
  </head>
  <body>
    <h1>LCWAIKIKI Classic Siyah %100 Pamuk Regular Fit Basic Tişört - S60418Z8-CVL</h1>
    <h2>Erkek Tişört</h2>
    <div>299,99 TL</div>
    <div>Renk: Yeni Siyah</div>
    <div>Renk seçenekleri</div>
    <a href="/100-pamuk-regular-fit-basic-tisort-beyaz-o-4869998">
      <img src="https://cdn.lcw.com/color-beyaz.jpg" alt="Beyaz" />
    </a>
    <div>Beden:</div>
    <div>XS  S  M  L  XL  2XL</div>
    <div>Ürün Açıklaması</div>
    <div>Kampanyalar</div>
    <div>: S60418Z8-CVL - Siyah</div>
    <div>Standart kalıplı erkek tişört, bisiklet yaka ve kısa kolludur.</div>
    <div>Yumuşak dokulu kuması ile günlük kullanım için uygundur.</div>
    <div>Manken Bilgisi</div>
    <div>Uzunluk 189 cm Göğüs 96 cm Bel 77 cm</div>
    <div>Ürün İçeriği ve Özellikleri</div>
    <div>Marka: LCWAIKIKI Classic</div>
    <div>Ürün Tipi: Tişört</div>
    <div>Cinsiyet: Erkek</div>
    <div>Malzeme: %100 Pamuk</div>
    <img src="https://img-lcwaikiki.mncdn.com/mnpadding/1020/1360/ffffff/pim/productimages/20261/8355849/v1/l_20261-s60418z8-cvl_a.jpg" alt="LCWAIKIKI Classic Siyah %100 Pamuk Regular Fit Basic Tişört" />
    <img src="https://img-lcwaikiki.mncdn.com/mnpadding/1020/1360/ffffff/pim/productimages/20261/8355849/v1/l_20261-s60418z8-cvl_a1.jpg" alt="LCWAIKIKI Classic Siyah %100 Pamuk Regular Fit Basic Tişört" />
  </body>
</html>
"""


LCW_DETAIL_WITH_EMBEDDED_VARIANTS_HTML = """
<html>
  <head>
    <title>LCW ACCESSORIES Lacivert LA Nakışlı Erkek Kep Şapka - S6CT56Z8-CRP | LCW</title>
    <meta property="og:title" content="LCW ACCESSORIES Lacivert LA Nakışlı Erkek Kep Şapka - S6CT56Z8-CRP | LCW" />
    <meta property="og:image" content="https://img-lcwaikiki.mncdn.com/mnpadding/320/426/ffffff/pim/productimages/20261/8601991/v2/l_20261-s6ct56z8-crp_a.jpg" />
  </head>
  <body>
    <script>
      var productData = {
        "ProductOptionList":[
          {"OptionId":5044153,"MainColorName":"Lacivert","Title":"Lacivert","Url":"/la-nakisli-erkek-kep-sapka-lacivert-o-5044153"},
          {"OptionId":5047394,"MainColorName":"Beyaz","Title":"Beyaz","Url":"/la-nakisli-erkek-cocuk-kep-sapka-beyaz-o-5047394"}
        ]
      };
      var fakeText = "Renk seçenekleri";
    </script>
    <h1>LCW ACCESSORIES Lacivert LA Nakışlı Erkek Kep Şapka - S6CT56Z8-CRP</h1>
    <h2>Şapka-Erkek</h2>
    <div>399,99 TL</div>
    <div>Renk: Lacivert</div>
    <div>Beden:</div>
    <div>Standart</div>
    <div>Ürün Açıklaması</div>
    <div>: S6CT56Z8-CRP - Lacivert</div>
    <div>Nakış detaylı erkek kep şapka günlük kullanım için uygundur.</div>
    <div>Ürün İçeriği ve Özellikleri</div>
    <div>Marka: LCW ACCESSORIES</div>
    <div>Ürün Tipi: Kep Şapka</div>
    <img src="https://img-lcwaikiki.mncdn.com/mnpadding/1020/1360/ffffff/pim/productimages/20261/8601991/v2/l_20261-s6ct56z8-crp_a.jpg" alt="LCW ACCESSORIES Lacivert LA Nakışlı Erkek Kep Şapka" />
  </body>
</html>
"""


LCW_DETAIL_WITH_DISABLED_SIZES_HTML = """
<html>
  <head>
    <title>LCW ACCESSORIES Hakiki Deri Erkek Kemer - S6F922Z8-HKK | LCW</title>
    <meta property="og:title" content="LCW ACCESSORIES Hakiki Deri Erkek Kemer - S6F922Z8-HKK | LCW" />
    <meta property="og:image" content="https://img-lcwaikiki.mncdn.com/mnpadding/320/426/ffffff/pim/productimages/20261/9999999/v1/l_20261-s6f922z8-hkk_a.jpg" />
  </head>
  <body>
    <h1>LCW ACCESSORIES Hakiki Deri Erkek Kemer - S6F922Z8-HKK</h1>
    <h2>Kemer</h2>
    <div>499,99 TL</div>
    <div>Renk: Kahverengi</div>
    <div>Beden:</div>
    <button>85</button>
    <button disabled>95</button>
    <button aria-disabled="true">105</button>
    <button class="size-button passive">115</button>
    <button>125</button>
    <div>Sepete Ekle</div>
    <div>Ürün Açıklaması</div>
    <div>: S6F922Z8-HKK - Kahverengi</div>
    <div>Erkek kemer, deri kumaştan üretilmiştir.</div>
    <div>Ürün İçeriği ve Özellikleri</div>
    <div>Marka: LCW ACCESSORIES</div>
    <div>Ürün Tipi: Kemer</div>
    <img src="https://img-lcwaikiki.mncdn.com/mnpadding/1020/1360/ffffff/pim/productimages/20261/9999999/v1/l_20261-s6f922z8-hkk_a.jpg" alt="LCW ACCESSORIES Hakiki Deri Erkek Kemer" />
  </body>
</html>
"""


def _white_cap_variant_html():
    return (
        LCW_DETAIL_WITH_EMBEDDED_VARIANTS_HTML
        .replace("Lacivert", "Beyaz")
        .replace("S6CT56Z8-CRP", "S6CT56Z8-ZUY")
        .replace("5044153", "5047394", 1)
        .replace("5047394", "5044153", 1)
        .replace(
            "/la-nakisli-erkek-kep-sapka-lacivert-o-5044153",
            "/la-nakisli-erkek-cocuk-kep-sapka-beyaz-o-5047394",
            1,
        )
        .replace(
            "/la-nakisli-erkek-cocuk-kep-sapka-beyaz-o-5047394",
            "/la-nakisli-erkek-kep-sapka-lacivert-o-5044153",
            1,
        )
        .replace("s6ct56z8-crp_a.jpg", "s6ct56z8-zuy_a.jpg")
    )


LCW_HOME_HTML = """
<html>
  <body>
    <a href="/erkek-tisort-t-345">Erkek Tisort</a>
    <a href="/kadin-elbise-t-120">Kadin Elbise</a>
    <a href="/magaza/lc-waikiki-s-1">Magaza</a>
  </body>
</html>
"""


def _white_variant_html():
    return (
        LCW_DETAIL_HTML.replace("Yeni Siyah", "Beyaz")
        .replace("S60418Z8-CVL", "S60418Z8-Q6K")
        .replace("Siyah", "Beyaz")
        .replace("s60418z8-cvl_a.jpg", "s60418z8-q6k_a.jpg")
        .replace("s60418z8-cvl_a1.jpg", "s60418z8-q6k_a1.jpg")
        .replace(
            '<a href="/100-pamuk-regular-fit-basic-tisort-beyaz-o-4869998">\n      <img src="https://cdn.lcw.com/color-beyaz.jpg" alt="Beyaz" />\n    </a>',
            '<a href="/100-pamuk-regular-fit-basic-tisort-siyah-o-4827603"><img src="https://cdn.lcw.com/color-siyah.jpg" alt="Siyah" /></a>',
        )
    )


def _haki_variant_html():
    return (
        LCW_DETAIL_HTML.replace("Yeni Siyah", "Haki")
        .replace("S60418Z8-CVL", "S60418Z8-HAK")
        .replace("Siyah", "Haki")
        .replace("s60418z8-cvl_a.jpg", "s60418z8-hak_a.jpg")
        .replace("s60418z8-cvl_a1.jpg", "s60418z8-hak_a1.jpg")
        .replace(
            '<a href="/100-pamuk-regular-fit-basic-tisort-beyaz-o-4869998">\n      <img src="https://cdn.lcw.com/color-beyaz.jpg" alt="Beyaz" />\n    </a>',
            '<a href="/100-pamuk-regular-fit-basic-tisort-siyah-o-4827603"><img src="https://cdn.lcw.com/color-siyah.jpg" alt="Siyah" /></a>',
        )
    )


def test_lcw_category_and_product_url_detection():
    assert LcwParser.is_lcw_category_url("https://www.lcw.com/erkek-tisort-t-345")
    assert LcwParser.is_lcw_product_url("https://www.lcw.com/100-pamuk-regular-fit-basic-tisort-siyah-o-4827603")
    assert not LcwParser.is_lcw_category_url("https://www.lcw.com/magaza/lc-waikiki-s-1")


def test_parse_categories_from_homepage(monkeypatch):
    parser = LcwParser()
    monkeypatch.setattr(parser, "_make_request", lambda url, **kwargs: LCW_HOME_HTML)

    categories = parser.parse_categories()

    assert [item["url"] for item in categories] == [
        "https://www.lcw.com/erkek-tisort-t-345",
        "https://www.lcw.com/kadin-elbise-t-120",
    ]


def test_parse_product_detail(monkeypatch):
    parser = LcwParser()

    def fake_make_request(url, **kwargs):
        if url.endswith("4869998"):
            return _white_variant_html()
        return LCW_DETAIL_HTML

    monkeypatch.setattr(parser, "_make_request", fake_make_request)

    product = parser.parse_product_detail(
        "https://www.lcw.com/100-pamuk-regular-fit-basic-tisort-siyah-o-4827603"
    )

    assert product is not None
    assert product.name == "LCWAIKIKI Classic Siyah %100 Pamuk Regular Fit Basic Tişört - S60418Z8-CVL"
    assert product.external_id == "lcw-4827603"
    assert product.sku == "S60418Z8"
    assert product.brand == "LCWAIKIKI Classic"
    assert product.category == "Erkek Tişört"
    assert product.currency == "TRY"
    assert product.price == 299.99
    assert product.description == (
        "Siyah Standart kalıplı erkek tişört, bisiklet yaka ve kısa kolludur. "
        "Yumuşak dokulu kuması ile günlük kullanım için uygundur."
    )
    assert product.attributes["og_image_url"] == (
        "https://img-lcwaikiki.mncdn.com/mnpadding/320/426/ffffff/pim/productimages/20261/8355849/v1/l_20261-s60418z8-cvl_a.jpg"
    )
    assert product.images == [
        "https://img-lcwaikiki.mncdn.com/mnpadding/1020/1360/ffffff/pim/productimages/20261/8355849/v1/l_20261-s60418z8-cvl_a.jpg",
        "https://img-lcwaikiki.mncdn.com/mnpadding/1020/1360/ffffff/pim/productimages/20261/8355849/v1/l_20261-s60418z8-cvl_a1.jpg",
    ]
    assert product.attributes["malzeme"] == "%100 Pamuk"
    assert product.attributes["variant_group_id"] == "lcw-4827603"
    assert len(product.attributes["fashion_variants"]) == 2
    assert product.attributes["fashion_variants"][0]["color"] == "Yeni Siyah"
    assert product.attributes["fashion_variants"][0]["sizes"][0]["size"] == "XS"
    assert product.attributes["fashion_variants"][1]["external_id"] == "lcw-var-4869998"


def test_parse_product_list_uses_group_ids_to_deduplicate(monkeypatch):
    parser = LcwParser()

    def fake_make_request(url, **kwargs):
        if url.endswith("-t-345"):
            return LCW_CATEGORY_HTML
        if url.endswith("4869998"):
            return _white_variant_html()
        if url.endswith("-4827604"):
            return (
                LCW_DETAIL_HTML.replace("4827603", "4827604")
                .replace("S60418Z8-CVL", "S99999Z8-MAV")
                .replace("Yeni Siyah", "Saks")
                .replace("Siyah", "Saks")
            )
        return LCW_DETAIL_HTML

    monkeypatch.setattr(parser, "_make_request", fake_make_request)

    products = parser.parse_product_list("https://www.lcw.com/erkek-tisort-t-345")

    assert len(products) == 2
    assert products[0].external_id == "lcw-4827603"
    assert products[1].external_id == "lcw-4827604"


def test_parse_product_detail_keeps_disabled_sizes_with_zero_stock(monkeypatch):
    parser = LcwParser()
    monkeypatch.setattr(parser, "_make_request", lambda url, **kwargs: LCW_DETAIL_WITH_DISABLED_SIZES_HTML)

    product = parser.parse_product_detail("https://www.lcw.com/hakiki-deri-erkek-kemer-kahverengi-o-5373706")

    assert product is not None
    sizes = product.attributes["fashion_variants"][0]["sizes"]
    assert sizes == [
        {"size": "85", "is_available": True, "stock_quantity": 1000, "sort_order": 0},
        {"size": "95", "is_available": False, "stock_quantity": 0, "sort_order": 1},
        {"size": "105", "is_available": False, "stock_quantity": 0, "sort_order": 2},
        {"size": "115", "is_available": False, "stock_quantity": 0, "sort_order": 3},
        {"size": "125", "is_available": True, "stock_quantity": 1000, "sort_order": 4},
    ]
    assert product.attributes["fashion_variants"][0]["stock_quantity"] == 1000


def test_parse_product_list_skips_variant_urls_already_seen_in_same_family(monkeypatch):
    parser = LcwParser()

    def fake_make_request(url, **kwargs):
        if url.endswith("-t-345"):
            return LCW_CATEGORY_WITH_SAME_FAMILY_VARIANTS_HTML
        if url.endswith("4869998"):
            return _white_variant_html()
        if url.endswith("-4827604"):
            return (
                LCW_DETAIL_HTML.replace("4827603", "4827604")
                .replace("S60418Z8-CVL", "S99999Z8-MAV")
                .replace("Yeni Siyah", "Saks")
                .replace("Siyah", "Saks")
            )
        return LCW_DETAIL_HTML

    monkeypatch.setattr(parser, "_make_request", fake_make_request)

    products = parser.parse_product_list("https://www.lcw.com/erkek-tisort-t-345")

    assert len(products) == 2
    assert [product.external_id for product in products] == [
        "lcw-4827603",
        "lcw-4827604",
    ]


def test_parse_product_list_skips_second_root_url_for_same_family_by_group_sku(monkeypatch):
    parser = LcwParser()

    category_html = """
    <html>
      <body>
        <a href="/100-pamuk-regular-fit-basic-tisort-siyah-o-4827603">Siyah</a>
        <a href="/100-pamuk-regular-fit-basic-tisort-haki-o-5214738">Haki</a>
        <a href="/soft-touch-tisort-saks-o-4827604">Saks</a>
      </body>
    </html>
    """

    request_counts = {"haki": 0}

    def fake_make_request(url, **kwargs):
        if url.endswith("-t-345"):
            return category_html
        if url.endswith("5214738"):
            request_counts["haki"] += 1
            return _haki_variant_html()
        if url.endswith("-4827604"):
            return (
                LCW_DETAIL_HTML.replace("4827603", "4827604")
                .replace("S60418Z8-CVL", "S99999Z8-MAV")
                .replace("Yeni Siyah", "Saks")
                .replace("Siyah", "Saks")
            )
        return LCW_DETAIL_HTML

    monkeypatch.setattr(parser, "_make_request", fake_make_request)

    products = parser.parse_product_list("https://www.lcw.com/erkek-tisort-t-345")

    assert len(products) == 2
    assert [product.external_id for product in products] == [
        "lcw-4827603",
        "lcw-4827604",
    ]
    assert request_counts["haki"] == 1


def test_parse_product_detail_collects_variants_from_embedded_json_when_dom_links_missing(monkeypatch):
    parser = LcwParser()

    def fake_make_request(url, **kwargs):
        if url.endswith("5047394"):
            return _white_cap_variant_html()
        return LCW_DETAIL_WITH_EMBEDDED_VARIANTS_HTML

    monkeypatch.setattr(parser, "_make_request", fake_make_request)

    product = parser.parse_product_detail(
        "https://www.lcw.com/la-nakisli-erkek-kep-sapka-lacivert-o-5044153"
    )

    assert product is not None
    assert product.external_id == "lcw-5044153"
    assert product.attributes["variant_group_id"] == "lcw-5044153"
    assert len(product.attributes["fashion_variants"]) == 2
    assert [variant["external_id"] for variant in product.attributes["fashion_variants"]] == [
        "lcw-var-5044153",
        "lcw-var-5047394",
    ]
    assert [variant["color"] for variant in product.attributes["fashion_variants"]] == [
        "Lacivert",
        "Beyaz",
    ]
