from apps.scrapers.parsers.ilacfiyati import IlacFiyatiParser


def test_ilacfiyati_parser_fetches_instruction_tabs(monkeypatch):
    base_url = "https://ilacfiyati.com"
    product_url = f"{base_url}/ilaclar/zovirax-5-krem-2-gr"
    parser = IlacFiyatiParser(base_url=base_url)

    main_html = """
    <html><head><meta property="og:image" content="/img/zovirax.png"></head><body>
      <h1>ZOVIRAX %5 KREM (2 GR)</h1>
      <table>
        <tr><td>İLAÇ FİYATI</td><td>152,62 TL</td></tr>
        <tr><td>FİRMA ADI</td><td>Glaxosmithkline İlaçları San. Ve Tic. A.Ş.</td></tr>
        <tr><td>BARKOD</td><td>8699522352692</td></tr>
        <tr><td>ETKİN MADDE</td><td>Asiklovir</td></tr>
        <tr><td>ATC KODU</td><td>D06BB03</td></tr>
        <tr><td>FORMU</td><td>Dermatolojik Krem</td></tr>
        <tr><td>UYGULAMA YOLU</td><td>Topikal</td></tr>
        <tr><td>RAF ÖMRÜ</td><td>24 Ay</td></tr>
        <tr><td>REÇETE</td><td>Beyaz Reçete</td></tr>
      </table>
    </body></html>
    """
    tab_pages = {
        "ozet": "<h3>ZOVİRAX KREM %5 KULLANMA TALİMATI</h3><p>Cilt üzerine uygulanır.</p>",
        "ne-icin-kullanilir": "<h3>1. ZOVİRAX NEDİR VE NE İÇİN KULLANILIR?</h3><p>ZOVİRAX, antiviral bir ilaçtır.</p>",
        "kullanmadan-dikkat-edilecekler": "<h3>2. ZOVİRAX'I KULLANMADAN ÖNCE DİKKAT EDİLMESİ GEREKENLER</h3><p>Asiklovire alerjiniz varsa kullanmayınız.</p>",
        "nasil-kullanilir": "<h3>3. ZOVİRAX NASIL KULLANILIR?</h3><p>Doktorunuzun söylediği şekilde kullanınız.</p>",
        "yan-etkileri": "<h3>4. OLASI YAN ETKİLER NELERDİR?</h3><p>Kaşıntı görülebilir.</p>",
        "saklanmasi": "<h3>5. ZOVİRAX'IN SAKLANMASI</h3><p>25°C altındaki oda sıcaklığında saklayınız.</p>",
        "ilac-bilgileri": "<h3>İLAÇ BİLGİLERİ</h3><p>BARKOD 8699522352692</p>",
        "esdegeri": """
          <h3>EŞDEĞERİ</h3>
          <table>
            <tr>
              <td><a href="/ilaclar/asiviral-400-mg-25-tablet">ASIVIRAL 400 MG 25 TABLET</a></td>
              <td>Barkod: 8699546090114</td>
              <td>ATC Kodu: D06BB03</td>
              <td>SGK Eşdeğer Kodu: E007D</td>
            </tr>
          </table>
        """,
    }

    responses = {product_url: main_html, f"{product_url}/sgk-esdegeri": ""}
    responses.update(
        {
            f"{product_url}/{path}": f"<html><body>{html}<h6>İlaç Katılım Payı Hesaplama</h6></body></html>"
            for path, html in tab_pages.items()
        }
    )

    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    monkeypatch.setattr(parser, "_make_request", lambda url: responses.get(url.rstrip("/"), ""))

    product = parser.parse_product_detail(product_url)

    assert product is not None
    assert product.name == "ZOVIRAX %5 KREM (2 GR)"
    assert "Özet:" in product.description
    assert "Ne İçin Kullanılır:" in product.description
    assert "Kullanmadan Dikkat Edilecekler:" in product.description
    assert "Nasıl Kullanılır:" in product.description
    assert "Yan Etkileri:" in product.description
    assert "Saklanması:" in product.description
    assert product.attributes["source_tabs"]["indications"]["text"].startswith("1. ZOVİRAX")
    assert "Doktorunuzun söylediği" in product.attributes["usage_instructions_source"]
    assert "Kaşıntı görülebilir" in product.attributes["side_effects_source"]
    assert "25°C" in product.attributes["storage_conditions_source"]
    assert product.analogs == [
        {
            "name": "ASIVIRAL 400 MG 25 TABLET",
            "url": "https://ilacfiyati.com/ilaclar/asiviral-400-mg-25-tablet",
            "price": None,
            "external_id": "asiviral-400-mg-25-tablet",
            "source_tab": "Eşdeğeri",
            "barcode": "8699546090114",
            "atc_code": "D06BB03",
            "sgk_equivalent_code": "E007D",
        }
    ]


def test_ilacfiyati_parser_uses_product_slug_as_external_id_for_tab_urls():
    base_url = "https://ilacfiyati.com"
    tab_url = f"{base_url}/ilaclar/lasirin-20-mg-tablet-20-tablet/ilac-bilgileri"
    parser = IlacFiyatiParser(base_url=base_url)

    assert parser._extract_external_id_from_url(tab_url) == "lasirin-20-mg-tablet-20-tablet"
