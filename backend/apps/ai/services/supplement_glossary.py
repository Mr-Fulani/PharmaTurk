"""Словарь турецких слов в названиях БАДов ilacfiyati → RU / EN.

Модель получает переводы слов, найденных в названии (``glossary_for``), и не
угадывает их: в пилоте 25.10.2026 Haiku перевела KEREVIZ (сельдерей) как «конский
каштан», ÇEMEN TOHUMU (пажитник) — как «семена кассии». Для веществ («s») проверка
результата требует их перевод в названии (``missing_terms``); описательные слова
(«d»: масло, экстракт, порошок, вкус) только подсказываются.

Ключ — слова после ``fold_tr`` (нижний регистр, без турецких букв); сочетания
проверяются раньше отдельных слов. Состав словаря — частые слова названий 7 883 БАДов
каталога (25.10.2026); новое слово добавляется строкой без правки кода.
"""

from __future__ import annotations

import re
from typing import Any

from apps.ai.services.medicine_reference import fold_tr

S, D = "s", "d"

GLOSSARY: dict[str, tuple[str, str, str]] = {
    # ── Сочетания ──
    "kara murver": ("чёрная бузина", "black elderberry", S),
    "karamurver": ("чёрная бузина", "black elderberry", S),
    "balik yagi": ("рыбий жир", "fish oil", S),
    "morina baligi": ("печень трески", "cod liver", S),
    "corek otu": ("чернушка (чёрный тмин)", "black seed / black cumin / nigella", S),
    "corekotu": ("чернушка (чёрный тмин)", "black seed / black cumin / nigella", S),
    "ari sutu": ("маточное молочко", "royal jelly", S),
    "arisutu": ("маточное молочко", "royal jelly", S),
    "uzum cekirdegi": ("виноградные косточки", "grape seed", S),
    "kabak cekirdegi": ("тыквенные семечки", "pumpkin seed", S),
    "keten tohumu": ("семена льна", "flaxseed", S),
    "cemen tohumu": ("пажитник", "fenugreek", S),
    "cuce palmiye": ("карликовая пальма (сереноа)", "saw palmetto / serenoa", S),
    "deve dikeni": ("расторопша", "milk thistle", S),
    "devedikeni": ("расторопша", "milk thistle", S),
    "turna yemisi": ("клюква", "cranberry", S),
    "kudret nari": ("горькая дыня (момордика)", "bitter melon / momordica", S),
    "hindistan cevizi": ("кокос", "coconut", S),
    "keci boynuzu": ("рожковое дерево (кэроб)", "carob / locust bean", S),
    "keciboynuzu": ("рожковое дерево (кэроб)", "carob / locust bean", S),
    "keciboynuzlu": ("с кэробом", "with carob", S),
    "afrika sardunyasi": ("пеларгония сидовидная", "African geranium (Pelargonium sidoides)", S),
    "yer fistigi": ("арахис", "peanut", S),
    "antep fistigi": ("фисташка", "pistachio", S),
    "kara dut": ("чёрная шелковица", "black mulberry", S),
    "karadut": ("чёрная шелковица", "black mulberry", S),
    "frenk uzumu": ("чёрная смородина", "blackcurrant", S),
    "yaban mersini": ("черника", "bilberry / blueberry", S),
    "meyan koku": ("корень солодки", "licorice root", S),
    "yumurta kabugu zari": ("мембрана яичной скорлупы", "eggshell membrane", S),
    "yumurta kabugu": ("яичная скорлупа", "eggshell", S),
    "keci sutu": ("козье молоко", "goat milk", S),
    "devam sutu": ("последующая молочная смесь", "follow-on formula", S),
    "bebek mamasi": ("детская смесь", "infant formula", S),
    "folik asit": ("фолиевая кислота", "folic acid", S),
    "hyaluronik asit": ("гиалуроновая кислота", "hyaluronic acid", S),
    "lipoik asit": ("липоевая кислота", "lipoic acid", S),
    "omega 3 yag asitleri": ("жирные кислоты омега-3", "omega-3 fatty acids", S),
    "yag asitleri": ("жирные кислоты", "fatty acids", S),
    "amino asit": ("аминокислоты", "amino acids", S),
    "koenzim q10": ("коэнзим Q10", "coenzyme Q10", S),
    "tibbi mantar": ("лекарственные грибы", "medicinal mushrooms", S),
    "deniz yosunu": ("морские водоросли", "seaweed", S),
    "turuncgil bioflavonoidleri": ("цитрусовые биофлавоноиды", "citrus bioflavonoids", S),
    "soguk pres": ("холодного отжима", "cold-pressed", D),
    "karisik meyve": ("смесь фруктов", "mixed fruit", D),
    "agizda dagilan": ("диспергируемые во рту", "orally disintegrating", D),
    "gaz giderici": ("ветрогонный", "anti-flatulence", D),
    "emziren anneler": ("для кормящих матерей", "for breastfeeding mothers", D),
    "film kapli": ("покрытые оболочкой", "film-coated", D),
    # ── Минералы ──
    "cinko": ("цинк", "zinc", S),
    "magnezyum": ("магний", "magnesium", S),
    "demir": ("железо", "iron", S),
    "kalsiyum": ("кальций", "calcium", S),
    "selenyum": ("селен", "selenium", S),
    "iyot": ("йод", "iodine", S),
    "krom": ("хром", "chromium", S),
    "bakir": ("медь", "copper", S),
    "manganez": ("марганец", "manganese", S),
    "potasyum": ("калий", "potassium", S),
    "sodyum": ("натрий", "sodium", S),
    "fosfor": ("фосфор", "phosphorus", S),
    "bor": ("бор", "boron", S),
    # ── Вещества ──
    "probiyotik": ("пробиотик", "probiotic", S),
    "probiotik": ("пробиотик", "probiotic", S),
    "prebiyotik": ("пребиотик", "prebiotic", S),
    "prebiotik": ("пребиотик", "prebiotic", S),
    "mikroorganizma": ("микроорганизмы", "microorganisms", S),
    "bakteri": ("бактерии", "bacteria", S),
    "kollajen": ("коллаген", "collagen", S),
    "kolajen": ("коллаген", "collagen", S),
    "kollagen": ("коллаген", "collagen", S),
    "kollajeni": ("коллаген", "collagen", S),
    "peptitleri": ("пептиды", "peptides", S),
    "glukozamin": ("глюкозамин", "glucosamine", S),
    "glikozamin": ("глюкозамин", "glucosamine", S),
    "kondroitin": ("хондроитин", "chondroitin", S),
    "kuersetin": ("кверцетин", "quercetin", S),
    "kurkumin": ("куркумин", "curcumin", S),
    "astaksantin": ("астаксантин", "astaxanthin", S),
    "likopen": ("ликопин", "lycopene", S),
    "zeaksantin": ("зеаксантин", "zeaxanthin", S),
    "sitikolin": ("цитиколин", "citicoline", S),
    "fosfatidilserin": ("фосфатидилсерин", "phosphatidylserine", S),
    "fosfotidilserin": ("фосфатидилсерин", "phosphatidylserine", S),
    "kolin": ("холин", "choline", S),
    "betain": ("бетаин", "betaine", S),
    "taurin": ("таурин", "taurine", S),
    "glutatyon": ("глутатион", "glutathione", S),
    "l-glutatyon": ("L-глутатион", "L-glutathione", S),
    "l-arjinin": ("L-аргинин", "L-arginine", S),
    "l-arginin": ("L-аргинин", "L-arginine", S),
    "arginin": ("аргинин", "arginine", S),
    "l-karnitin": ("L-карнитин", "L-carnitine", S),
    "karnitin": ("карнитин", "carnitine", S),
    "l-lizin": ("L-лизин", "L-lysine", S),
    "l-teanin": ("L-теанин", "L-theanine", S),
    "l-glutamin": ("L-глутамин", "L-glutamine", S),
    "l-sistein": ("L-цистеин", "L-cysteine", S),
    "l-sistin": ("L-цистин", "L-cystine", S),
    "l-karnosin": ("L-карнозин", "L-carnosine", S),
    "glisin": ("глицин", "glycine", S),
    "metilkobalamin": ("метилкобаламин", "methylcobalamin", S),
    "metilfolat": ("метилфолат", "methylfolate", S),
    "kolekalsiferol": ("холекальциферол", "cholecalciferol", S),
    "menakuinon": ("менахинон", "menaquinone", S),
    "laktoferrin": ("лактоферрин", "lactoferrin", S),
    "kolostrum": ("молозиво (колострум)", "colostrum", S),
    "lisozim": ("лизоцим", "lysozyme", S),
    "laktaz": ("лактаза", "lactase", S),
    "inulin": ("инулин", "inulin", S),
    "betaglukan": ("бета-глюкан", "beta-glucan", S),
    "glukan": ("глюкан", "glucan", S),
    "spirulina": ("спирулина", "spirulina", S),
    "kafein": ("кофеин", "caffeine", S),
    "elektrolit": ("электролиты", "electrolytes", S),
    "jelatin": ("желатин", "gelatin", S),
    "keratin": ("кератин", "keratin", S),
    "elastin": ("эластин", "elastin", S),
    "pepsin": ("пепсин", "pepsin", S),
    "melatonin": ("мелатонин", "melatonin", S),
    "biotin": ("биотин", "biotin", S),
    "inositol": ("инозитол", "inositol", S),
    "polen": ("пыльца", "pollen", S),
    "propolis": ("прополис", "propolis", S),
    "propolisli": ("с прополисом", "with propolis", S),
    "bal": ("мёд", "honey", S),
    "balli": ("с мёдом", "with honey", S),
    "maya": ("дрожжи", "yeast", S),
    "lif": ("клетчатка", "fiber", S),
    "protein": ("протеин", "protein", S),
    "piperin": ("пиперин", "piperine", S),
    "karvakrol": ("карвакрол", "carvacrol", S),
    "sukrozomiyal": ("сукросомальное", "sucrosomial", D),
    # ── Растения, плоды, специи ──
    "zerdecal": ("куркума", "turmeric", S),
    "zencefil": ("имбирь", "ginger", S),
    "zencefilli": ("с имбирём", "with ginger", S),
    "kekik": ("тимьян (чабрец)", "thyme / oregano", S),
    "nane": ("мята", "mint", S),
    "rezene": ("фенхель", "fennel", S),
    "anason": ("анис", "anise", S),
    "tarcin": ("корица", "cinnamon", S),
    "karanfil": ("гвоздика", "clove", S),
    "biberiye": ("розмарин", "rosemary", S),
    "adacayi": ("шалфей", "sage", S),
    "papatya": ("ромашка", "chamomile", S),
    "ihlamur": ("липа", "linden", S),
    "melisa": ("мелисса", "lemon balm", S),
    "enginar": ("артишок", "artichoke", S),
    "kantaron": ("зверобой", "St. John's wort", S),
    "kusburnu": ("шиповник", "rose hip", S),
    "hatmi": ("алтей", "marshmallow", S),
    "karahindiba": ("одуванчик", "dandelion", S),
    "kimyon": ("тмин", "cumin", S),
    "susam": ("кунжут", "sesame", S),
    "cemen": ("пажитник", "fenugreek", S),
    "kereviz": ("сельдерей", "celery", S),
    "dereotu": ("укроп", "dill", S),
    "kisnis": ("кориандр", "coriander", S),
    "defne": ("лавр", "laurel", S),
    "feslegen": ("базилик", "basil", S),
    "ardic": ("можжевельник", "juniper", S),
    "okaliptus": ("эвкалипт", "eucalyptus", S),
    "lavanta": ("лаванда", "lavender", S),
    "safran": ("шафран", "saffron", S),
    "aspir": ("сафлор", "safflower", S),
    "keten": ("лён", "flax", S),
    "kenevir": ("конопля", "hemp", S),
    "badem": ("миндаль", "almond", S),
    "ceviz": ("грецкий орех", "walnut", S),
    "findik": ("фундук", "hazelnut", S),
    "isirgan": ("крапива", "nettle", S),
    "ekinezya": ("эхинацея", "echinacea", S),
    "murver": ("бузина", "elderberry / elder", S),
    "menengic": ("фисташка терпентинная (менгенич)", "terebinth", S),
    "alic": ("боярышник", "hawthorn", S),
    "kizilcik": ("кизил", "cornelian cherry", S),
    "sakiz": ("мастиковая смола", "mastic gum", S),
    "mersin": ("мирт", "myrtle", S),
    "hashas": ("мак", "poppy", S),
    "sarimsak": ("чеснок", "garlic", S),
    "yosunu": ("водоросли", "algae", S),
    "mantari": ("грибы", "mushrooms", S),
    "tahil": ("злаки", "cereals", S),
    "lepidyum": ("лепидиум (мака)", "lepidium (maca)", S),
    "pelargonium": ("пеларгония", "pelargonium", S),
    "kahve": ("кофе", "coffee", S),
    "incir": ("инжир", "fig", D),
    "elma": ("яблоко", "apple", D),
    "nar": ("гранат", "pomegranate", S),
    "limon": ("лимон", "lemon", D),
    "limonlu": ("с лимоном", "lemon", D),
    "portakal": ("апельсин", "orange", D),
    "portakalli": ("с апельсином", "orange", D),
    "mandalina": ("мандарин", "mandarin", D),
    "muz": ("банан", "banana", D),
    "cilek": ("клубника", "strawberry", D),
    "ahududu": ("малина", "raspberry", D),
    "visne": ("вишня", "sour cherry", D),
    "seftali": ("персик", "peach", D),
    "kayisi": ("абрикос", "apricot", D),
    "karpuz": ("арбуз", "watermelon", D),
    "ananas": ("ананас", "pineapple", D),
    "uzum": ("виноград", "grape", D),
    "kabak": ("тыква", "pumpkin", D),
    "cikolata": ("шоколад", "chocolate", D),
    "vanilya": ("ваниль", "vanilla", D),
    # ── Описательные слова ──
    "yagi": ("масло", "oil", D),
    "yag": ("масло", "oil", D),
    "yaglar": ("масла", "oils", D),
    "zeytinyagi": ("оливковое масло", "olive oil", S),
    "ekstresi": ("экстракт", "extract", D),
    "ekstrakti": ("экстракт", "extract", D),
    "ekstre": ("экстракт", "extract", D),
    "ektresi": ("экстракт", "extract", D),
    "ekstreleri": ("экстракты", "extracts", D),
    "ekstreler": ("экстракты", "extracts", D),
    "ekstraktlari": ("экстракты", "extracts", D),
    "ekstreli": ("с экстрактом", "with extract", D),
    "ozu": ("экстракт", "extract", D),
    "tozu": ("порошок", "powder", D),
    "toz": ("порошок", "powder", D),
    "cayi": ("чай", "tea", D),
    "cay": ("чай", "tea", D),
    "suyu": ("сок / вода", "juice / water", D),
    "surubu": ("сироп", "syrup", D),
    "surup": ("сироп", "syrup", D),
    "damla": ("капли", "drops", D),
    "sprey": ("спрей", "spray", D),
    "spreyi": ("спрей", "spray", D),
    "sivi": ("жидкий", "liquid", D),
    "likit": ("жидкий", "liquid", D),
    "macunu": ("паста", "paste", D),
    "pekmezi": ("пекмез (сироп из плодов)", "molasses", D),
    "suspansiyon": ("суспензия", "suspension", D),
    "solusyon": ("раствор", "solution", D),
    "aromali": ("со вкусом", "flavoured", D),
    "meyveli": ("фруктовый", "fruit", D),
    "karisimi": ("смесь", "blend", D),
    "karisim": ("смесь", "blend", D),
    "bitkisel": ("растительный", "herbal", D),
    "bitki": ("растения", "plants", D),
    "tohumu": ("семена", "seed", D),
    "cekirdegi": ("косточки / семена", "seed", D),
    "yapragi": ("листья", "leaf", D),
    "koku": ("корень", "root", D),
    "cicegi": ("цветки", "flower", D),
    "kabugu": ("кора / кожура", "bark / peel", D),
    "meyvesi": ("плоды", "fruit", D),
    "zari": ("мембрана", "membrane", D),
    "sade": ("без вкуса", "plain", D),
    "sekersiz": ("без сахара", "sugar-free", D),
    "tatlandirici": ("подсластитель", "sweetener", D),
    "tatlandirilmis": ("подслащённый", "sweetened", D),
    "dogal": ("натуральный", "natural", D),
    "organik": ("органический", "organic", D),
    "sizma": ("первого отжима", "extra virgin", D),
    "dilalti": ("подъязычный", "sublingual", D),
    "cignenebilir": ("жевательный", "chewable", D),
    "cigneme": ("жевательный", "chewable", D),
    "efervesan": ("шипучий", "effervescent", D),
    "yumusak": ("мягкий", "soft", D),
    "patlatilabilen": ("с капсулой, которую можно раскусить", "burstable", D),
    "lipozomal": ("липосомальный", "liposomal", D),
    "mikroenkapsule": ("микрокапсулированный", "microencapsulated", D),
    "enterik": ("кишечнорастворимый", "enteric", D),
    "hidrolize": ("гидролизованный", "hydrolyzed", D),
    "enzimatik": ("ферментативный", "enzymatic", D),
    "standardize": ("стандартизированный", "standardized", D),
    "bazli": ("на основе", "based", D),
    "vitamini": ("витамин", "vitamin", D),
    "vitaminleri": ("витамины", "vitamins", D),
    "vitaminler": ("витамины", "vitamins", D),
    "vitaminli": ("с витамином", "with vitamin", D),
    "mineraller": ("минералы", "minerals", D),
    "aminoasit": ("аминокислоты", "amino acids", S),
    "asit": ("кислота", "acid", D),
    "asitleri": ("кислоты", "acids", D),
    "sitrat": ("цитрат", "citrate", D),
    "bisglisinat": ("бисглицинат", "bisglycinate", D),
    "pikolinat": ("пиколинат", "picolinate", D),
    "malat": ("малат", "malate", D),
    "sulfat": ("сульфат", "sulfate", D),
    "fosfat": ("фосфат", "phosphate", D),
    "kompleks": ("комплекс", "complex", D),
    "kompleksi": ("комплекс", "complex", D),
    "bebek": ("для младенцев", "for babies", D),
    "cocuk": ("для детей", "for children", D),
    "cocuklar": ("для детей", "for children", D),
    "yetiskin": ("для взрослых", "for adults", D),
    "anneler": ("для матерей", "for mothers", D),
    "hamile": ("для беременных", "for pregnant women", D),
    "kadin": ("для женщин", "for women", D),
    "kadinlar": ("для женщин", "for women", D),
    "erkek": ("для мужчин", "for men", D),
    "erkekler": ("для мужчин", "for men", D),
    "bogaz": ("горло", "throat", D),
    "burun": ("нос", "nose", D),
    "agiz": ("рот", "mouth", D),
    "sac": ("волосы", "hair", D),
    "oksuruk": ("от кашля", "cough", D),
    "gece": ("ночной", "night", D),
    "gunduz": ("дневной", "day", D),
    "kirmizi": ("красный", "red", D),
    "yesil": ("зелёный", "green", D),
    "sari": ("жёлтый", "yellow", D),
    "kara": ("чёрный", "black", D),
    "beyaz": ("белый", "white", D),
    "sigir": ("говяжий", "bovine", D),
    "mentol": ("ментол", "menthol", D),
    "mentollu": ("с ментолом", "with menthol", D),
}

_KEYS = sorted(GLOSSARY, key=lambda key: -len(key.split()))


def _words(text: Any) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9\-]*", fold_tr(text))


def found_terms(text: Any) -> list[str]:
    """Ключи словаря, найденные в тексте: сочетания раньше их отдельных слов, без повторов."""
    words = _words(text)
    used = [False] * len(words)
    found = []
    for key in _KEYS:
        parts = key.split()
        size = len(parts)
        for start in range(len(words) - size + 1):
            if words[start:start + size] == parts and not any(used[start:start + size]):
                used[start:start + size] = [True] * size
                if key not in found:
                    found.append(key)
    return found


def glossary_for(text: Any) -> dict[str, str]:
    """{слово источника: "ru | en"} для подсказки модели."""
    return {key.upper(): f"{GLOSSARY[key][0]} | {GLOSSARY[key][1]}" for key in found_terms(text)}


def _normalized(text: Any) -> str:
    """Нижний регистр, «ё» → «е», без дефисов: «Бета-глюкан» = «бетаглюкан»."""
    return str(text or "").lower().replace("ё", "е").replace("-", "")


def _stems(text: str) -> list[str]:
    words = [w for w in re.findall(r"[a-zа-я0-9]+", _normalized(text)) if len(w) > 3]
    return [w[: max(4, len(w) - 2)] for w in words]


def _alternatives(term: str) -> list[str]:
    """«чернушка (чёрный тмин)» → ["чернушка", "чёрный тмин"]; «black seed / nigella» → два варианта."""
    return [part.strip() for part in re.split(r" / |\(|\)", term) if part.strip()]


def _has(text: str, term: str) -> bool:
    return any(all(stem in text for stem in _stems(option)) for option in _alternatives(term))


def missing_terms(source_middle: Any, product_ru: Any, product_en: Any) -> list[str]:
    """Вещества словаря из названия, перевода которых (любого варианта) нет в RU или EN «что это»."""
    ru, en = _normalized(product_ru), _normalized(product_en)
    return [
        key
        for key in found_terms(source_middle)
        if GLOSSARY[key][2] == S and not (_has(ru, GLOSSARY[key][0]) and _has(en, GLOSSARY[key][1]))
    ]
