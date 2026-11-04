"""Память переводов БАДов: состав, способ применения, предупреждения, хранение.

Разделы страницы БАДа (``source_tabs``) у разных товаров повторяются не абзацами, а
частями: компоненты состава («Kolekalsiferol (D3 vitamini)», «Kapsül (sığır
jelatini)») и типовые фразы этикетки («Tavsiye edilen günlük porsiyonu aşmayın.»).
Замер на 372 карточках источника 05.11.2026: повторяется половина компонентов
состава. Поэтому единица памяти — компонент состава или одно предложение раздела,
namespace ``supplement_line``.

Код находит в разделах четыре блока (по подписям «Ürün Bileşimi:», «Kullanım
Şekli:», «Uyarılar:», «Muhafaza Koşulları:» и по типовым фразам без подписи),
берёт готовые переводы из памяти, а новые переводит модель короткими
нумерованными запросами с проверкой сдвига ответа — как абзацы инструкций
лекарств (``medicine_memory.translate_paragraphs``). Блок попадает в карточку,
только если переведены все его части.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from apps.ai.services import medicine_memory
from apps.ai.services.medicine_reference import fold_tr
from apps.ai.services.translation_memory import lookup, normalize_source_text, remember

LINE_NAMESPACE = "supplement_line"
BLOCK_KINDS = ("composition", "excipients", "usage", "warnings", "storage")
BLOCK_TITLES = {
    "composition": ("Состав", "Ingredients"),
    "excipients": ("Вспомогательные вещества", "Other ingredients"),
    "usage": ("Способ применения", "How to use"),
    "warnings": ("Предупреждения", "Warnings"),
    "storage": ("Хранение", "Storage"),
}
UNIT_MAX_CHARS = 400

LINE_SYSTEM_PROMPT = (
    "Ты переводчик этикеток биологически активных добавок (БАД). Переводи с турецкого на русский "
    "и английский компоненты состава и строки этикетки: способ применения, предупреждения, условия "
    "хранения. Каждый элемент переводи полностью и отдельно: не сокращай, не пересказывай, не "
    "объединяй и ничего не добавляй. Сохраняй каждое число, единицу, процент и код пищевой добавки "
    "(E 551). Русский — естественный язык этикетки: «Tavsiye edilen günlük porsiyonu aşmayın» = "
    "«Не превышайте рекомендуемую суточную порцию», «Çocukların ulaşamayacağı yerde saklayın» = "
    "«Хранить в недоступном для детей месте». Вещества — принятыми названиями: «kolekalsiferol» = "
    "холекальциферол / cholecalciferol, «hacim arttırıcı» = наполнитель / bulking agent, «topaklanmayı "
    "önleyici» = антислёживающий агент / anti-caking agent, «takviye edici gıda» = БАД / food supplement. "
    "Латинские названия бактерий и растений (Lactobacillus acidophilus) оставляй латиницей. "
    "Ответ — строго JSON."
)

# Подписи разделов на странице БАДа (``fold_tr``, без двоеточия). Подпись другого
# раздела («Ürün Adı», «Özet Bilgi») закрывает текущий блок.
_LABELS = {
    "composition": (
        "urun bilesimi", "urun bilesenleri", "icerik", "icerigi", "icindekiler", "diger icerikler",
        "bilesenler", "bilesimi",
    ),
    "usage": (
        "kullanim sekli", "kullanim onerisi", "onerilen kullanim", "tavsiye edilen kullanim",
        "gunluk kullanim dozu", "kullanim talimati", "kullanim",
    ),
    "warnings": ("uyarilar", "uyari", "onemli uyarilar", "dikkat", "alerjen uyarisi"),
    "storage": ("muhafaza kosullari", "saklama kosullari", "muhafaza", "saklama"),
}
_LABEL_KIND = {label: kind for kind, labels in _LABELS.items() for label in labels}
_LABEL_RE = re.compile(r"^([^:]{2,40}?)\s*:\s*(.*)$")

# Типовые фразы без подписи («Takviye edici gıdalar normal beslenmenin yerine geçemez.»).
_STANDARD_WARNING_RE = re.compile(
    r"asma(?:yin|yiniz)|yerine gec|ulasamayacag|hamile|emzir|doktor|hekim|alerj|"
    r"kullanilmamal|tuketilmemeli|onerilmez"
)
# «serin» — словом: «Fosfotidilserin» — вещество, а не «прохладное место».
_STANDARD_STORAGE_RE = re.compile(r"\bserin\b|\bkuru yer|muhafaza ed|sakla(?:yin|yiniz)|°c|gunes isig")
# То же, что «биологически активная добавка, не является лекарственным средством» дисклеймера
# карточки (DISCLAIMER).
_DISCLAIMER_DUPLICATE_RE = re.compile(
    r"ilac degil|hastaliklarin onlenmesi|tedavi edilmesi amaciyla|takviyesidir|takviye edici gidadir"
)
# Срок годности и номер партии на упаковке — не предупреждение («Tavsiye Edilen Tüketim Tarihinden (TETT)
# önce tüketiniz», «Parti No … kutunun alt yüzündedir»).
_PACKAGE_DATA_RE = re.compile(r"\btett\b|tuketim tarih|son kullanma|parti no|seri no|lot no|uretim tarih")
# Вспомогательные вещества: список из одних них (SOLGAR «İçindekiler: Kapsül (…), topaklanmayı önleyici (…)»,
# действующее вещество — в таблице доз) подписывается не «Состав».
_EXCIPIENT_RE = re.compile(
    r"^(?:kapsul|kaplama|hacim art|dolgu|topaklan|stabiliz|emulgat|jellest|tatlandir|aroma|koruyucu|renklendir|"
    r"kivam|nem verici|parlatici|asitlik duzenley|antioksidan|sigir jelatin|balik jelatin|jelatin|gliserin|"
    r"silikon dioksit|magnezyum stearat|mikrokristalin|hidroksipropil)"
)
# Строка таблицы состава, а не компонент: «270 mg», «mg», «%76,00», «Her 10 ml için».
_UNIT_RE = re.compile(r"(?<![^\W\d_])(?:mg|mcg|µg|g|gr|ml|iu|ui|ie|kob|cfu|kcal|kj)(?![^\W\d_])")
_QUANTITY_ONLY_RE = re.compile(r"[\d\s.,%/x×()*-]*")
_PORTION_HEADER_RE = re.compile(r"\bicin$")  # «Her 10 ml için», «2 tablet için»
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ0-9«\"(])")


@dataclass
class SupplementBlocks:
    """Блоки раздела: {вид: [исходные части]} и переводы готовых блоков."""

    parts: dict[str, list[str]] = field(default_factory=dict)
    ru: dict[str, list[str]] = field(default_factory=dict)
    en: dict[str, list[str]] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)


def _split_top_level(text: str) -> list[str]:
    """Список состава → компоненты: запятая или точка с запятой вне скобок."""
    items, depth, current = [], 0, []
    for index, char in enumerate(text):
        if char in "([":
            depth += 1
        elif char in ")]":
            depth = max(0, depth - 1)
        # «1,3 - 1,6 Beta Glukan», «%0,91»: запятая между цифрами — десятичная.
        decimal = char == "," and text[index - 1 : index].isdigit() and text[index + 1 : index + 2].isdigit()
        if char in ",;" and depth == 0 and not decimal:
            items.append("".join(current))
            current = []
        else:
            current.append(char)
    items.append("".join(current))
    result = []
    for item in items:
        item = item.strip(" .*")
        folded = fold_tr(item)
        # «FEROGLOBİN … İçeren Sıvı Takviye Edici Gıda - 200 ml» — название товара, а не компонент.
        if re.search(r"[^\W\d_]{2}", item) and not (
            _QUANTITY_ONLY_RE.fullmatch(_UNIT_RE.sub("", folded)) or _PORTION_HEADER_RE.search(folded)
            or _DISCLAIMER_DUPLICATE_RE.search(folded)
            or "takviye edici gida" in folded
        ):
            result.append(item)
    return result


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_SPLIT_RE.split(text) if re.search(r"[^\W\d_]{2}", part)]


def _label_kind(label: str) -> Optional[str]:
    """Подпись с двоеточием → вид блока: точная из словаря или по началу
    («Kullanım şekli ve Günlük alım dozu», «Ürün İçeriği (1 Stik Saşe)»)."""
    if label in _LABEL_KIND:
        return _LABEL_KIND[label]
    if label.startswith("kullanim") or "gunluk alim" in label or "gunluk kullanim" in label:
        return "usage"
    if label.startswith("uyari"):
        return "warnings"
    if "saklama" in label or "muhafaza" in label:
        return "storage"
    if "bilesim" in label or label.startswith(("icerik", "icindekiler", "urun icerigi")):
        return "composition"
    return None


def _label(line: str) -> tuple[Optional[str], str, bool]:
    """Строка → (вид блока или None, текст после подписи, это подпись)."""
    bare = fold_tr(line).strip(" *:")
    # Подпись без двоеточия («Muhafaza Koşulları») — только из двух слов и больше:
    # «İçerik» без двоеточия — заголовок столбца таблицы состава.
    if bare in _LABEL_KIND and " " in bare:
        return _LABEL_KIND[bare], "", True
    match = _LABEL_RE.match(line)
    if not match:
        return None, line, False
    kind = _label_kind(fold_tr(match.group(1)).strip(" *"))
    if kind:
        return kind, match.group(2).strip(), True
    # Подпись другого раздела («Ürün Adı:», «Menşe Ülke: Kanada») — короткая, без точки внутри;
    # текст после неё проверяется на типовые фразы.
    if len(match.group(1).split()) <= 5 and "." not in match.group(1):
        return None, match.group(2).strip(), True
    return None, line, False


# Заголовок таблицы доз или пищевой ценности после списка состава: «Etken Madde», «Miktar / 10ml»,
# «%BRD», «1 Kapsül İçeriği», «Her bitkisel kapsülde», «Besin Enerjisi» — список закончился.
_TABLE_HEADER_RE = re.compile(
    r"miktar|etken madde|brd\b|\brda\b|besin|enerji|icerigi|bilesen adi|supplement facts|"
    r"^her\b|\bicin$|^bilesenler$|^icindekiler$"
)
_LOWER_START_RE = re.compile(r"^[a-zçğıöşü]")


def section_parts(sections: dict[str, str]) -> dict[str, list[str]]:
    """Разделы источника → {вид блока: части по порядку, без повторов}."""
    parts: dict[str, list[str]] = {kind: [] for kind in BLOCK_KINDS}
    for text in sections.values():
        current: Optional[str] = None
        list_seen = False  # в составе уже была строка-список «A, B, C»
        filled = False  # у текущей подписи уже есть текст
        open_part: Optional[tuple[str, int]] = None  # предложение без точки в конце — его продолжение ниже
        for raw in str(text or "").split("\n"):
            line = normalize_source_text(raw)
            if not line:
                continue
            # Фраза, разрезанная переносом: «Tavsiye edilen» / «günlük alım dozunu aşmayınız.»
            if open_part and _LOWER_START_RE.match(line):
                kind, index = open_part
                joined = _sentences(f"{parts[kind][index]} {line}")
                parts[kind][index:index + 1] = joined
                last = index + len(joined) - 1
                open_part = None if re.search(r"[.!?;:]$", parts[kind][last]) else (kind, last)
                continue
            open_part = None
            kind, rest, is_label = _label(line)
            if is_label:
                current, list_seen, filled = kind, False, False
                if not rest:
                    continue
                line = rest
            elif current == "composition":
                if _TABLE_HEADER_RE.search(fold_tr(line)) or (list_seen and len(_split_top_level(line)) < 2):
                    current = None
            # Короткая строка без точки после текста способа применения или предупреждений — уже
            # таблица или заголовок («Form», «Tablet», «Raf Ömrü Bilgisi»): блок закончился.
            elif current is not None and filled and len(line.split()) < 4 and not re.search(r"[.!]$", line):
                current = None
            filled = True
            if current == "composition":
                items = _split_top_level(line)
                list_seen = list_seen or len(items) > 1
                parts["composition"].extend(items)
                continue
            for sentence in _sentences(line):
                folded = fold_tr(sentence)
                if _DISCLAIMER_DUPLICATE_RE.search(folded) or _PACKAGE_DATA_RE.search(folded) or sentence.endswith("?"):
                    continue
                target = current
                if target is None:
                    if _STANDARD_STORAGE_RE.search(folded) and not re.search(r"ulasamayacag", folded):
                        target = "storage"
                    elif _STANDARD_WARNING_RE.search(folded):
                        target = "warnings"
                if target:
                    parts[target].append(sentence)
                    open_part = None if re.search(r"[.!?;:]$", sentence) else (target, len(parts[target]) - 1)
    if parts["composition"] and all(_EXCIPIENT_RE.match(fold_tr(item)) for item in parts["composition"]):
        parts["excipients"], parts["composition"] = parts["composition"], []
    return {
        kind: list(dict.fromkeys(item for item in items if len(item) <= UNIT_MAX_CHARS))
        for kind, items in parts.items()
        if items
    }


def translate_blocks(sections: dict[str, str], llm) -> tuple[SupplementBlocks, dict[str, Any]]:
    """Части блоков — из памяти, новые — моделью; блок готов, если переведены все его части.

    → (блоки, usage запросов перевода). ``llm=None`` — только память.
    """
    blocks = SupplementBlocks(parts=section_parts(sections))
    units = list(dict.fromkeys(unit for items in blocks.parts.values() for unit in items))
    found = lookup(LINE_NAMESPACE, units) if units else {}
    cached = len(found)
    missing = [unit for unit in units if unit not in found]
    usage: dict[str, Any] = {"tokens": {}, "cost_usd": 0.0, "processing_time_ms": 0}
    rejected: dict[str, list[str]] = {}
    if missing and llm is not None:
        accepted, rejected, usage = medicine_memory.translate_paragraphs(
            missing, llm, system_prompt=LINE_SYSTEM_PROMPT
        )
        if accepted:
            remember(LINE_NAMESPACE, accepted)
            found.update(accepted)
    for kind, items in blocks.parts.items():
        if all(item in found for item in items):
            blocks.ru[kind] = [found[item]["ru"] for item in items]
            blocks.en[kind] = [found[item]["en"] for item in items]
    blocks.stats = {
        "units": len(units),
        "cached": cached,
        "translated": len([unit for unit in missing if unit in found]),
        "rejected": {unit[:120]: reasons for unit, reasons in rejected.items()},
        "missing": len([unit for unit in units if unit not in found]),
        "blocks": sorted(blocks.ru),
        "incomplete_blocks": sorted(set(blocks.parts) - set(blocks.ru)),
    }
    return blocks, usage
