from apps.scrapers.parsers.lcw import LcwParser


LCW_PERFUME_DETAIL_WITH_GALLERY_LINKS_HTML = """
<html>
  <head>
    <title>LCW ACCESSORIES Parfüm - 9W1948Z8-CRP | LCW</title>
    <meta property="og:title" content="LCW ACCESSORIES Parfüm - 9W1948Z8-CRP | LCW" />
    <meta property="og:image" content="https://img-lcwaikiki.mncdn.com/mnpadding/320/426/ffffff/productimages/20192/1/3570787/l_20192-9w1948z8-crp_a.jpg" />
  </head>
  <body>
    <h1>LCW ACCESSORIES Parfüm - 9W1948Z8-CRP</h1>
    <h2>Parfüm</h2>
    <div>89,99 TL</div>
    <div>Renk: Lacivert</div>
    <div>Beden:</div>
    <div>Standart</div>
    <div>Ürün Açıklaması</div>
    <div>: 9W1948Z8-CRP - Lacivert</div>
    <div>Odunsu erkek parfüm günlük kullanım için uygundur.</div>
    <div>Ürün İçeriği ve Özellikleri</div>
    <div>Marka: LCW ACCESSORIES</div>
    <div>Ürün Tipi: Parfüm</div>
    <img src="https://img-lcwaikiki.mncdn.com/mnpadding/1020/1360/ffffff/productimages/20192/1/3570787/l_20192-9w1948z8-crp_a.jpg" alt="Parfüm" />
    <a href="https://img-lcwaikiki.mncdn.com/mnpadding/1020/1360/ffffff/productimages/20192/1/3570787/l_20192-9w1948z8-crp_b.jpg">Parfüm-1</a>
  </body>
</html>
"""


def test_parse_product_detail_collects_perfume_gallery_links(monkeypatch):
    parser = LcwParser()
    monkeypatch.setattr(parser, "_make_request", lambda url, **kwargs: LCW_PERFUME_DETAIL_WITH_GALLERY_LINKS_HTML)

    product = parser.parse_product_detail("https://www.lcw.com/parfum-lacivert-o-623703")

    assert product is not None
    assert product.images == [
        "https://img-lcwaikiki.mncdn.com/mnpadding/1020/1360/ffffff/productimages/20192/1/3570787/l_20192-9w1948z8-crp_a.jpg",
        "https://img-lcwaikiki.mncdn.com/mnpadding/1020/1360/ffffff/productimages/20192/1/3570787/l_20192-9w1948z8-crp_b.jpg",
    ]
