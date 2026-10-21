"""Категория аксессуаров Zara и витрин Inditex по данным API.

Задачи этих парсеров сохраняют товары в «Одежду» (категория конфигурации), но в
тех же листингах есть сумки, кошельки, ремни, украшения и шапки. Massimo Dutti
21.10 сохранил косметичку «Büyük napa deri makyaj çantası» как одежду.

API отдаёт семейство товара: у Zara ``familyName`` «CANTA», ``subfamilyName``
«Z1:BAGS LARGE»; у Massimo Dutti ``familyNameEN`` «BAGS AND BACKPACKS»,
``subFamilyNameEN`` «TRAVEL ITEMS» (турецкое ``familyName`` там «DERİ DIŞ
GİYİM» — неверно) и отдел закупки ``purchaser`` «COMPLEMENTOS». В турецком
названии главное слово стоит последним. Английское название не используем:
«Midi dress with belt» кончается словом «belt», но это платье.

Результат — slug категорий от точной к корню типа; сервис берёт первую
существующую (``ScraperIntegrationService._apply_category_mapping``).
"""

import re
import unicodedata
from typing import Iterable, List

# Slug по виду товара; ключ пола — из раздела витрины (men/women).
_KIND_SLUGS = {
    "backpack": {"men": ["acc-mens-backpacks", "mens-bags"], "women": ["acc-womens-backpacks", "womens-bags"]},
    "belt_bag": {"men": ["acc-mens-belt-bags", "mens-bags"], "women": ["acc-belt-bags", "womens-bags"]},
    "bag": {"men": ["mens-bags"], "women": ["womens-bags"]},
    "belt": {"men": ["mens-belts"], "women": ["womens-belts"]},
}
_KIND_TAIL = {
    "backpack": ["bags-wallets", "accessories"],
    "belt_bag": ["bags-wallets", "accessories"],
    "bag": ["bags-wallets", "accessories"],
    "suitcase": ["suitcases", "travel-bags", "bags-wallets", "accessories"],
    "card_holder": ["card-holders", "wallets", "bags-wallets", "accessories"],
    "wallet": ["wallets", "bags-wallets", "accessories"],
    "belt": ["belts", "accessories"],
    "scarf": ["scarves-shawls", "accessories"],
    "gloves": ["acc-gloves", "accessories"],
    "sunglasses": ["sunglasses", "eyewear", "accessories"],
    "umbrella": ["umbrellas", "accessories"],
    "tie": ["neckties", "ties-pocket-squares", "accessories"],
    "accessory": ["accessories"],
    "earrings": ["earrings", "jewelry"],
    "necklace": ["necklaces", "jewelry"],
    "bracelet": ["bracelets", "jewelry"],
    "ring": ["rings", "jewelry"],
    "brooch": ["brooches", "jewelry"],
    "jewelry": ["jewelry"],
    "hat": ["headwear"],
}

# Последнее слово турецкого названия (после _fold: без диакритики, нижний регистр).
_NAME_TAIL_RULES = [
    (r"bel cantasi", "belt_bag"),
    (r"sirt cantasi", "backpack"),
    (r"valiz(?:i)?", "suitcase"),
    (r"kartlik(?:i)?", "card_holder"),
    (r"cuzdan(?:i)?", "wallet"),
    (r"canta(?:si)?", "bag"),
    (r"kemer(?:i)?", "belt"),
    (r"(?:atki|sal|esarp|fular)(?:si|i)?", "scarf"),
    (r"eldiven(?:i|leri)?", "gloves"),
    (r"gozlu(?:k|gu)", "sunglasses"),
    (r"semsiye(?:si)?", "umbrella"),
    (r"(?:kravat|papyon)(?:i|u)?", "tie"),
    (r"kupe(?:si|ler)?", "earrings"),
    (r"kolye(?:si)?", "necklace"),
    (r"(?:bileklik|bilezik)(?:i)?", "bracelet"),
    (r"yuzuk(?:u)?", "ring"),
    (r"bros(?:u)?", "brooch"),
    (r"(?:sapka|bere|kep|kasket)(?:si|i)?", "hat"),
]

# Семейство/подсемейство API: слово в любом месте метки.
_LABEL_RULES = [
    (r"\bbel cantasi\b|\brinoneras?\b|\b(?:belt|bum) bags?\b", "belt_bag"),
    (r"\bsirt cantasi\b|\bbackpacks?\b|\bmochilas?\b", "backpack"),
    (r"\bvaliz\w*|\bsuitcases?\b|\bmaletas?\b", "suitcase"),
    (r"\bkartlik\w*|\bcard ?holders?\b|\btarjeteros?\b", "card_holder"),
    (r"\bcuzdan\w*|\bwallets?\b|\bbilleteras?\b|\bmonederos?\b", "wallet"),
    (r"\bcanta\w*|\bbags?\b|\bbolsos?\b|\bneceser\w*", "bag"),
    (r"\bkemer\b|\bkemerler\b|\bbelts?\b|\bcinturon\w*", "belt"),
    (r"\batki\w*|\bsal\b|\besarp\w*|\bfular\w*|\bscar(?:f|ves)\b|\bbufandas?\b|\bfoulard\w*", "scarf"),
    (r"\beldiven\w*|\bgloves?\b|\bguantes?\b", "gloves"),
    (r"\bgozlu\w*|\bsunglasses\b|\bgafas\b", "sunglasses"),
    (r"\bsemsiye\w*|\bumbrellas?\b|\bparaguas\b", "umbrella"),
    (r"\bkravat\w*|\bpapyon\w*|\bcorbatas?\b|\bpajaritas?\b|\bneckties?\b", "tie"),
    (r"\bkupe\w*", "earrings"),
    (r"\bkolye\w*", "necklace"),
    (r"\bbileklik\w*|\bbilezik\w*", "bracelet"),
    (r"\byuzuk\w*", "ring"),
    (r"\btaki\b|\bmucevher\w*|\bbijuteri\b|\bbisuteria\b|\bbis\b|\bjewel(?:le)?ry\b|\bjoyeria\b", "jewelry"),
    (r"\bsapka\w*|\bbere\b|\bgorros?\b|\bgorras?\b|\bhats?\b|\bbeanies?\b", "hat"),
    (r"\baksesuar\w*|\bcomplementos?\b|\baccessories\b|\bseyahat\b|\btravel items?\b", "accessory"),
]

# Вид украшения внутри «бижутерии» (испанские/английские слова — только здесь:
# «collar» вне украшений — воротник).
_JEWELRY_DETAIL_RULES = [
    (r"\bkupe\w*|\bpendientes\b|\bearrings?\b", "earrings"),
    (r"\bkolye\w*|\bcollar(?:es)?\b|\bnecklaces?\b", "necklace"),
    (r"\bbileklik\w*|\bbilezik\w*|\bpulseras?\b|\bbracelets?\b", "bracelet"),
    (r"\byuzuk\w*|\banillos?\b|\brings?\b", "ring"),
    (r"\bbros\b|\bbroches?\b|\bbrooch(?:es)?\b", "brooch"),
]


def _fold(value) -> str:
    text = str(value or "")
    # «BAGSÂ ANDÂ BACKPACKS»: неразрывный пробел UTF-8, прочитанный как Latin-1.
    text = re.sub("Â(?=[\\s ])", " ", text).replace(" ", " ")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().replace("ı", "i")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _slugs(kind: str, gender: str) -> List[str]:
    return _KIND_SLUGS.get(kind, {}).get(gender, []) + _KIND_TAIL[kind]


def resolve_inditex_category_slugs(
    name: str,
    labels: Iterable[str] = (),
    gender: str = "",
) -> List[str]:
    """Slug категорий аксессуара (от точной к корню) или ``[]`` для одежды.

    ``labels`` — подсемейство, семейство и отдел закупки из API, от точного к
    общему.
    """
    folded_name = _fold(name)
    folded_labels = [label for label in (_fold(value) for value in labels) if label]
    kind = ""
    for pattern, rule_kind in _NAME_TAIL_RULES:
        if re.search(rf"(?:^| )(?:{pattern})$", folded_name):
            kind = rule_kind
            break
    if not kind:
        for label in folded_labels:
            kind = next((k for pattern, k in _LABEL_RULES if re.search(pattern, label)), "")
            if kind:
                break
    if kind == "jewelry":
        text = " ".join([folded_name, *folded_labels])
        kind = next((k for pattern, k in _JEWELRY_DETAIL_RULES if re.search(pattern, text)), kind)
    return _slugs(kind, gender) if kind else []
