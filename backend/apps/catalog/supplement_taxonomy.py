"""Подкатегория БАДа по турецкому названию источника — кодом, без LLM.

Категория определяет наценку и навигацию, поэтому AI её не меняет
(``AIResultApplier``), а раскладывает БАДы из корня «БАДы» по подкатегориям
это правило: команда ``assign_supplement_subcategories`` и парсер ilacfiyati
для новых товаров. Подкатегории наценку не задают (0) и наследуют её от корня.

Слова ищутся в названии после ``fold_tr`` (нижний регистр без турецких букв)
целыми словами. Сначала узкие группы, у которых состав говорит сам за себя
(детские, пробиотики, коллаген, омега); затем витамины/минералы/иммунитет/…
— побеждает слово, стоящее в названии раньше: «MAGNEZYUM VE B6» — минералы,
«D3 VITAMINI VE KALSIYUM» — витамины. Не распознано — товар остаётся в корне.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from apps.ai.services.medicine_reference import fold_tr
from apps.ai.services.supplement_content import is_baby_food

ROOT_SLUG = "supplements"
# Решение владельца 26.10.2026: дубль «Омега/рыбий жир» (omega-fish-oil) выключен.
OMEGA_SLUG = "omega-fatty-acids"


def _re(*words: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(words) + r")(?![a-z0-9])")


# Узкие группы: первая совпавшая побеждает.
PRIORITY_RULES: tuple[tuple[str, re.Pattern], ...] = (
    ("kids-supplements", _re(
        r"cocuk\w*", r"kids?", r"kinder", r"junior", r"bebek\w*", r"baby", r"infant", r"toddler",
        r"\d+\s*-\s*\d+\s*(?:ay|yas)", r"devam sutu", r"baslangic sutu",
    )),
    ("probiotics", _re(
        r"probi[yo]oti\w*", r"lactobacill\w*", r"bifido\w*", r"saccharomyces", r"kefir\w*",
        r"bakteri\w*", r"mikroorganizma\w*", r"reuteri", r"biogaia", r"acidophilus", r"flora", r"flor",
    )),
    ("collagen", _re(r"koll?ajen\w*", r"coll?agen\w*", r"kollagen\w*")),
    (OMEGA_SLUG, _re(
        r"omega\w*", r"balik yag\w*", r"fish oil", r"krill", r"morina\w*", r"cod liver",
        r"epa", r"dha",
    )),
)

# Общие группы: побеждает слово, стоящее в названии раньше.
POSITION_RULES: tuple[tuple[str, re.Pattern], ...] = (
    ("vitamins", _re(
        r"vitamin\w*", r"multivitamin\w*", r"[abcdek]\s?\d{0,2} vitamini", r"b\d{1,2}", r"d3", r"k2",
        r"biotin", r"folik asit", r"folat\w*", r"metilfolat", r"metilkobalamin", r"kolekalsiferol",
        r"menakuinon", r"b ?comple\w*", r"b ?kompleks\w*", r"d3 ?k2", r"hamile\w*", r"pregnan\w*",
        r"prenatal\w*", r"folic\w*", r"folik\w*",
    )),
    ("minerals", _re(
        r"magnezyum\w*", r"magnesium", r"cinko\w*", r"zinc", r"demir\w*", r"iron", r"ferro\w*",
        r"kalsiyum\w*", r"calcium", r"selenyum\w*", r"selenium", r"iyot\w*", r"krom\w*",
        r"potasyum\w*", r"multimineral\w*", r"mineral\w*", r"bakir", r"manganez", r"bor",
    )),
    ("immunity", _re(
        r"propolis\w*", r"ekinezya\w*", r"echinacea", r"kara ?murver\w*", r"murver\w*", r"elderberry",
        r"sambucus", r"beta ?glukan\w*", r"beta ?glucan", r"glukan", r"pelargonium", r"afrika sardunyasi",
        r"imm?un\w*", r"bagisiklik\w*", r"kolostrum", r"laktoferrin", r"kuersetin", r"quercetin",
        r"antioksidan\w*", r"antioxidant\w*", r"resveratrol", r"glutatyon", r"glutathione", r"astaksantin",
        r"lipoik asit", r"lipoic acid",
    )),
    ("energy-vitality", _re(
        r"koenzim q ?10", r"co-?enzyme q ?10", r"q ?10", r"coq\s?-?10", r"ginseng", r"zinseng", r"guarana",
        r"kafein", r"caffeine", r"lepidyum", r"lepidium", r"maca", r"enerji\w*", r"energy", r"ari ?sutu", r"royal jelly",
        r"taurin", r"rodiola", r"rhodiola",
    )),
    ("digestive-health", _re(
        r"sindirim\w*", r"enzim\w*", r"enzyme\w*", r"laktaz", r"lactase", r"bromelain", r"papain",
        r"pepsin", r"prebi[yo]oti\w*", r"inulin", r"psyllium", r"karniyarik otu", r"lif", r"fiber",
        r"fibre", r"simetikon", r"gaz giderici",
    )),
    ("protein-amino", _re(
        r"protein\w*", r"amino ?asit\w*", r"amino acid\w*", r"l-(?!glutat)\w+", r"arjinin", r"arginin\w*",
        r"karnitin", r"carnitine", r"glutamin\w*", r"lizin", r"teanin", r"glisin", r"sistein",
    )),
    ("sports-nutrition", _re(
        r"whey", r"kreatin\w*", r"creatine", r"bcaa", r"gainer", r"pre-?workout", r"sporcu\w*",
        r"izotonik", r"isotonic",
    )),
    ("herbal-supplements", _re(
        r"bitkisel", r"bitki\w*", r"herbal", r"ekstre\w*", r"ekstrakt\w*", r"extract", r"ozu",
        r"zerdecal", r"kurkumin", r"turmeric", r"curcumin", r"zencefil\w*", r"ginger", r"sarimsak",
        r"garlic", r"ginkgo", r"ashwagandha", r"corek ?otu\w*", r"deve ?dikeni", r"enginar",
        r"kekik\w*", r"isirgan", r"kusburnu", r"zeytin yapragi", r"olive leaf", r"yaprag\w*",
        r"tohum\w*", r"koku", r"root", r"cay\w*", r"tea", r"yag\w*", r"oil", r"passiflora", r"valerian\w*",
        r"kediotu", r"hatmi", r"ihlamur", r"cistus", r"berberin\w*", r"melisa", r"papatya", r"lavanta",
        r"nane", r"adacayi", r"rezene", r"chlorella", r"spirulina", r"karadut", r"kizilcik", r"maydanoz",
        r"cuce palmiye", r"saw palmetto", r"turna yemisi", r"cranberry", r"sakiz", r"mastik",
        r"safran", r"saffron", r"moringa", r"shilajit", r"berberis",
    )),
    # Суставы и сон: своей подкатегории нет — товар остаётся в корне, а не уходит
    # в «Пищеварение» из-за бромелайна или в «Витамины» из-за B6.
    (None, _re(
        r"glu[ck]o[sz]amin\w*", r"glikozamin", r"kondroitin", r"chondroitin", r"msm", r"melatonin\w*",
    )),
)

SUBCATEGORY_SLUGS = tuple(slug for slug, _ in PRIORITY_RULES + POSITION_RULES if slug)


def supplement_category_slug(source_name: Any, brand: Any = "") -> Optional[str]:
    """Slug подкатегории «БАДов» или None, если название ничего не говорит.

    Бренд в начале названия не учитывается: «İMUNEKS FARMA OSTEONEXT» — не иммунитет.
    """
    text = fold_tr(source_name)
    if not text or is_baby_food(text):
        return None
    prefix = fold_tr(brand)
    if prefix and text.startswith(prefix + " "):
        text = text[len(prefix) + 1:]
    for slug, pattern in PRIORITY_RULES:
        if pattern.search(text):
            return slug
    best = None
    for slug, pattern in POSITION_RULES:
        match = pattern.search(text)
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), slug)
    return best[1] if best else None
