"""Регрессия: LCW-парсер захватывает перфюм-спеки (Hacim/Koku Tipi/Paket İçeriği)
из блока «Ürün İçeriği ve Özellikleri», а энричмент проставляет volume и
fragrance_family.

Раньше блок парсился по одёжному whitelist (Ana Kumaş/Kumaş/Desen…) и перфюм-строки
выпадали → Объём пуст, а в описание шёл только одёжный мусор.
"""

from apps.scrapers.parsers.lcw import LcwParser
from apps.scrapers.services import ScraperIntegrationService


# Реальная структура страницы LCW (get_text("\n")): метка и значение на разных строках.
PERFUME_PAGE_TEXT = (
    "Ürün Açıklaması\n"
    "PARFUM1047-2 - 10231 - Renksiz\n"
    "2 adet gönderilmektedir. Elite Gentleman in Black EDT Eau de toilette "
    "Odunsu ve ferah koku\n"
    "Ürün İçeriği ve Özellikleri\n"
    "Satıcı:\nAvonShop\nMarka:\nAVON\nCinsiyet:\nErkek\n"
    "Paket İçeriği:\n2'li Paket\nHacim:\n75 ml\nKoku Tipi:\nOdunsu\n"
    "İmalatçı / İthalatçı / Yetkili Temsilci / İfa Hizmet Sağlayıcı: UCUZAVAR BİLGİ\n"
    "Kumaş Rehberi\nBakım Bilgileri\nGiysilerinizi Nasıl Yıkamalısınız?\nDestek\n"
)


def test_rich_description_captures_perfume_specs():
    parser = LcwParser(base_url="https://www.lcw.com")
    desc = parser._build_rich_description(PERFUME_PAGE_TEXT)
    assert "Hacim: 75 ml" in desc
    assert "Koku Tipi: Odunsu" in desc
    assert "Paket İçeriği: 2'li Paket" in desc


def test_enrichment_fills_volume_and_family_from_specs():
    parser = LcwParser(base_url="https://www.lcw.com")
    desc = parser._build_rich_description(PERFUME_PAGE_TEXT)

    service = ScraperIntegrationService()
    enriched = service._enrich_perfumery_attrs(
        {},
        name="Parfüm Seti - Markalar EDT 75 ml",
        description=desc,
        category="Parfüm",
        url="https://www.lcw.com/...-edt-75-ml-ikili-set-o-4098043",
    )
    assert enriched.get("volume") == "75 ml"
    assert enriched.get("fragrance_family") == "woody"
