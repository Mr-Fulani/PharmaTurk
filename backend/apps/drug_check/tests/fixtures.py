"""Фикстуры без сети: маленькие книги Excel в формате источников и фрагменты страниц IlacFiyati.

Книги собираются так же, как настоящие: строки — общие строки (sharedStrings), числа и даты —
числами (дата — серийный номер Excel). Колонки и листы — как в файлах от 10.11.2026.
"""

import io
import zipfile
from xml.sax.saxutils import escape

SKRS_TITLE = "SKRS E-REÇETE İLAÇ VE DİĞER FARMASÖTİK ÜRÜNLER LİSTESİ"
SKRS_HEAD = ["İlaç Adı", "Barkod", "ATC Kodu", "ATC Adı", "Firma Adı", "Reçete Türü", "Durumu", "Açıklama"]
ITS_REASON = "İTS'ye Göre Piyasada Bulunmadığından Pasife Alınmıştır."
CHANGED_NOTE = "Değişiklik Yapılan Ürünler listesinde açıklanan ürünler"

# 46336 = 10.11.2026, 45762 = 15.04.2025, 45951 = 21.10.2025, 41303 = 29.01.2013
NEXIUM = ["NEXIUM 40 MG ENTERIK KAPLI 14 PELLET TABLET", 8699786040021, "A02BC05", "esomeprazole",
          "ASTRAZENECA İLAÇ SAN.VE TİC.LTD.ŞTİ.", "Normal", "Pasif", None, 45762]
CRESTOR = ["CRESTOR 5 MG 28 FILM TABLET", 8699786090262, "C10AA07", "rosuvastatin",
           "ASTRAZENECA İLAÇ SAN.VE TİC.LTD.ŞTİ.", "Normal", "Pasif", None, 45951]
AKLAV = ["AKLAV BID 200 MG PEDIATRIK SUSPANSIYON", 8699591280063, "J01CR02", "amoxicillin",
         "BERKO İLAÇ VE KİMYA SAN. A.Ş.", "Normal", "Pasif", CHANGED_NOTE, 46336]
PAROL = ["PAROL 500 MG 30 TABLET", 8699717010093, "N02BE01", "paracetamol",
         "ATABAY KİMYA SANAYİ VE TİC. A.Ş.", "Normal", "Aktif", None, 0, 0, 0, 41303]
XARELTO = ["XARELTO 10 MG 10 FILM TABLET", 8699546093885, "B01AF01", "rivaroxaban",
           "BAYER TÜRK KİMYA SAN. LTD. ŞTİ.", "Normal", "Aktif", None, 0, 0, 0, 44320]


def make_xlsx(sheets: dict) -> bytes:
    """{имя листа: [строки]} → байты .xlsx. Строка ячейки — общая строка, число — число."""
    shared: list[str] = []

    def shared_index(text: str) -> int:
        if text not in shared:
            shared.append(text)
        return shared.index(text)

    def column(index: int) -> str:
        letters = ""
        index += 1
        while index:
            index, rest = divmod(index - 1, 26)
            letters = chr(65 + rest) + letters
        return letters

    sheet_xml = []
    for rows in sheets.values():
        body = []
        for r, row in enumerate(rows, start=1):
            cells = []
            for c, value in enumerate(row):
                ref = f"{column(c)}{r}"
                if value is None:
                    continue
                if isinstance(value, str):
                    cells.append(f'<c r="{ref}" t="s"><v>{shared_index(value)}</v></c>')
                else:
                    cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            body.append(f'<row r="{r}">{"".join(cells)}</row>')
        sheet_xml.append(
            '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/'
            f'spreadsheetml/2006/main"><sheetData>{"".join(body)}</sheetData></worksheet>'
        )
    names = list(sheets)
    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
        + "".join(f'<sheet name="{escape(n)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, n in enumerate(names))
        + "</sheets></workbook>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"'
            f' Target="worksheets/sheet{i + 1}.xml"/>'
            for i in range(len(names))
        )
        + "</Relationships>"
    )
    strings = (
        '<?xml version="1.0" encoding="UTF-8"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        + "".join(f"<si><t>{escape(s)}</t></si>" for s in shared)
        + "</sst>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as book:
        book.writestr("xl/workbook.xml", workbook)
        book.writestr("xl/_rels/workbook.xml.rels", rels)
        book.writestr("xl/sharedStrings.xml", strings)
        for i, xml in enumerate(sheet_xml):
            book.writestr(f"xl/worksheets/sheet{i + 1}.xml", xml)
    return buffer.getvalue()


def skrs_xlsx(active=(PAROL, XARELTO), passive=(NEXIUM, CRESTOR, AKLAV), changes=None, to_passive=()) -> bytes:
    if changes is None:
        changes = [AKLAV[:7] + [ITS_REASON]]
    return make_xlsx({
        "AKTİF ÜRÜNLER LİSTESİ": [
            [None, SKRS_TITLE], ["AKTİF ÜRÜNLER LİSTESİ (03.11.2026-09.11.2026)"],
            SKRS_HEAD + ["Temel İlaç Listesi Durumu", "Çocuk", "Yenidoğan", "Aktif Ürünler Listesine\nAlındığı Tarih"],
            *active,
        ],
        "PASİF ÜRÜNLER LİSTESİ": [
            [None, SKRS_TITLE], ["PASİF ÜRÜNLER LİSTESİ (03.11.2026-09.11.2026)"],
            SKRS_HEAD + ["Pasif Ürünler Listesine\nAlındığı Tarih"],
            *passive,
        ],
        "PASİFE ALINACAK ÜRÜNLER": [[None, SKRS_TITLE], ["PASİFE ALINACAK ÜRÜNLER LİSTESİ"], SKRS_HEAD, *to_passive],
        "LİSTEYE YENİ EKLENEN ÜRÜNLER": [[None, SKRS_TITLE], ["LİSTEYE YENİ EKLENEN ÜRÜNLER LİSTESİ"], SKRS_HEAD],
        "DEĞİŞİKLİK YAPILAN ÜRÜNLER": [[None, SKRS_TITLE], ["DEĞİŞİKLİK YAPILAN ÜRÜNLER LİSTESİ"], SKRS_HEAD, *changes],
    })


SELCUK_HEAD = ["BARKODU", "ILAC ADI", "FIYATI", "FIRMA", "TARIH", "KDV", "KURUM", "FIYAT TIPI", "ISK", " ISK.%", "KAR %"]


def selcuk_xlsx() -> bytes:
    # 46133 = 21.04.2026, 46113 = 01.04.2026
    return make_xlsx({"WEBLISTE": [
        SELCUK_HEAD,
        ["123123123x   ", "deneme ilaci", 3500, "", 46015, 10, 0, 2, "N", 0, 13.799],
        [8699717010093, "PAROL 500 MG 30 TB.           ", 105.16, "GENFAR         ", 46133, 10, 0, "B", "N", 0, 21.87],
        [8699546093885, "XARELTO 10 MG 10 TB.          ", 451.28, "BAYER PH       ", 46113, 10, 0, "B", "N", 0, 21.87],
        [8699593095085, "TOPAMAX 100 MG 60 TB.         ", 855.85, "ZZZ URETILMEYEN", 46113, 10, 0, "B", "N", 0, 21.87],
    ]})


TITCK_PAGE = """<html><body><table>
<tr><td><a href="https://titck.gov.tr/storage/Archive/2026/dynamicModulesAttachment/AKLST0203.11.2026skrserecetilacvedigerfarmasotikurunler_fff8.xlsx">03.11</a></td></tr>
<tr><td><a href="https://titck.gov.tr/storage/Archive/2026/dynamicModulesAttachment/AKLST0210.11.2026skrserecetilacvedigerfarmasotikurunler_b09f.xlsx">10.11</a></td></tr>
<tr><td><a href="https://titck.gov.tr/storage/Archive/2026/dynamicModulesAttachment/RuhsatlBeeriTbbirnlerListesi12.11.2026.xlsx">реестр</a></td></tr>
</table></body></html>"""
TITCK_FILE_URL = (
    "https://titck.gov.tr/storage/Archive/2026/dynamicModulesAttachment/"
    "AKLST0210.11.2026skrserecetilacvedigerfarmasotikurunler_b09f.xlsx"
)

SELCUK_PAGE = """<html><body><p>Güncel ilaç fiyat ve barkod listesini indirmek için
<a href="/dosyalar/ilacfiyatvebarkod/WEBLISTE-13-10-2026.xlsx" target="_blank">tıklayınız</a></p></body></html>"""


def ilacfiyati_card(name="NEXIUM 40 MG ENTERIK KAPLI 14 PELLET TABLET", price="202,15 TL", date="01.04.2026",
                    barcode="8699786040021", status="Aktif") -> str:
    """Фрагмент карточки ilacfiyati.com (вёрстка 13.11.2026)."""

    def card(label, value):
        return (
            '<div class="col-6 col-xl-4"><div class="info-card h-100"><div class="w-100 overflow-hidden">'
            f'<p class="info-card__label">{label}</p><p class="info-card__value text-truncate">{value}</p>'
            "</div></div></div>"
        )

    date_label = (
        'Fiyat Geçerlilik Tarihi <i class="fa-solid fa-circle-info text-muted ms-1" data-bs-toggle="tooltip" '
        'data-bs-title="İlacın fiyatı en son bu tarihte değişmiş olup fiyatı günceldir."></i>'
    )
    return (
        '<html><body><h1 class="fs-2x">37 Binden Fazla İlaç ve Ürün Bilgisi</h1>'
        f'<h1 class="page-title text-primary mb-2">{name}</h1><div class="row">'
        + card("İlaç Fiyatı", price)
        + card(date_label, date)
        + card("Barkod", barcode)
        + card("Etkin Madde", "Esomeprazol")
        + card("İlaç Durumu", status)
        + card("Firma Adı", "Astrazeneca")
        + "</div></body></html>"
    )


def ilacfiyati_search(*slugs) -> str:
    """Фрагмент страницы поиска /tum-urunler?q=… (вёрстка 13.11.2026)."""
    cards = "".join(
        '<div class="col-12 col-md-6 col-xl-3"><div class="card h-100 border">'
        f'<a href="/ilaclar/{slug}"><span class="badge">AKTİF</span></a></div></div>'
        for slug in slugs
    )
    return (
        '<html><body><div class="col-lg-9"><div class="row g-3 mt-4">'
        '<div class="col-12 d-flex"><div><h2 class="h5 mb-1">Arama Sonuçları</h2></div></div>'
        f"{cards}</div></div></body></html>"
    )
