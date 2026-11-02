"""Пересборка словарей лекарств моделью: МНН (medicine_inn) и бренды кириллицей (medicine_brand). TD-031.

МНН сверяются с названиями Wikidata по коду АТХ, бренды пишутся так, как их ищут покупатели. Скептик
перепроверяет каждую часть, код отсекает негодное. Цифры и ловушки —
docs/MEDICINE_TRANSLATION_KNOWLEDGE_BASE.md.
"""

from __future__ import annotations

import csv
import os
import re
from collections import Counter, defaultdict

from django.db import transaction

from apps.ai.models import AITranslationMemory
from apps.ai.services.medicine_memory import INN_NAMESPACE, propagate_inn_translations, split_inn
from apps.ai.services.medicine_seo import BRAND_NAMESPACE
from apps.ai.services.medicine_title import _INN_TITLE_MAX, medicine_source_name, paragraph_brand, title_inn
from apps.ai.services.memory_review import read_results
from apps.ai.services.translation_memory import remember, source_hash

INN_CHUNK_SIZE = 40
BRAND_CHUNK_SIZE = 80
# Общеизвестные «Глицерин» и «Адреналин» вместо «Глицерол» и «Эпинефрин»; «Позаконазол» — верное МНН
# (модель предлагала «Посаконазол»). Решение 24.10.2026, повторная пересборка его не отменяет.
INN_KEEP = {"gliserin", "adrenalin", "posakonazol"}
_LATIN_ALLOWED_IN_RU = re.compile(r"\b[A-Za-z]{1,2}-?\d+\b|\b[A-Z]\b|\bOK-432\b")
_LATIN = re.compile(r"[A-Za-z]")
_CYRILLIC = re.compile(r"[А-Яа-яЁё]")
_BRAND_FORM = re.compile(r"\b(?:мг|мл|таблет|капсул|сироп|раствор|мазь|крем|ампул|флакон|спрей)\w*", re.I)


def _medicine_items():
    from apps.catalog.models import Product

    products = (
        Product.objects.filter(product_type="medicines")
        .select_related("medicine_item")
        .only("id", "name", "external_data", "medicine_item__active_ingredient", "medicine_item__atc_code")
    )
    for product in products.iterator(chunk_size=500):
        item = getattr(product, "medicine_item", None)
        if item:
            yield product, item


def export_inn() -> list[dict]:
    """Записи словаря МНН и коды АТХ лекарств с этим веществом (только чтение)."""
    products, atc = Counter(), defaultdict(Counter)
    for _, item in _medicine_items():
        parts = split_inn(item.active_ingredient)
        for part in parts:
            key = source_hash(part)
            products[key] += 1
            if item.atc_code:
                atc[key][(item.atc_code.strip().upper(), len(parts))] += 1
    return [
        {"id": record.pk, "tr": record.source_text, "ru": record.ru_text, "en": record.en_text,
         "products": products[record.source_hash],
         "atc": [[code, substances, count] for (code, substances), count in atc[record.source_hash].most_common(5)]}
        for record in AITranslationMemory.objects.filter(namespace=INN_NAMESPACE).order_by("pk")
    ]


def _read_csv(directory, name):
    path = os.path.join(directory, name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def wikidata_evidence(directory):
    """Выгрузки Wikidata (запросы — в базе знаний) → функция «код АТХ → доказательства»."""
    labels, aliases, who = defaultdict(list), defaultdict(lambda: {"ru": [], "en": []}), defaultdict(list)
    for row in _read_csv(directory, "wd_atc_labels.csv"):
        labels[row["code"].strip().upper()].append(row)
    for row in _read_csv(directory, "wd_atc_alias.csv"):
        found = aliases[row["item"]][row["lang"]]
        if row["alias"] not in found and len(found) < 6:
            found.append(row["alias"])
    for row in _read_csv(directory, "wd_who_inn.csv"):
        for code in filter(None, row["codes"].split("|")):
            who[code].append(f'{row["lang"]}: {row["inn"]}')

    def evidence(code):
        return [
            {"ru": row["ru"], "en": row["en"], "la": row["la"], "ru_aliases": aliases[row["item"]]["ru"],
             "en_aliases": aliases[row["item"]]["en"], "who_inn": who.get(code, [])[:3]}
            for row in labels.get(code, [])[:2]
        ]
    return evidence


def inn_chunks(export, evidence=None, size=INN_CHUNK_SIZE) -> list[dict]:
    """Части по коду АТХ: соли и формы одного вещества попадают вместе."""
    rows = [
        {"id": row["id"], "tr": row["tr"], "ru": row["ru"], "en": row["en"], "products": row["products"],
         "atc": [{"code": code, "substances_in_product": substances, "products": count,
                  "wikidata": evidence(code) if evidence else []}
                 for code, substances, count in row["atc"][:3]]}
        for row in export
    ]
    rows.sort(key=lambda row: (row["atc"][0]["code"] if row["atc"] else "~", row["tr"]))
    return [{"k": start // size, "items": rows[start:start + size]} for start in range(0, len(rows), size)]


def _answers(result_paths) -> tuple[dict, Counter]:
    stats, usage = Counter(), Counter()
    answers = {}
    for found in read_results(result_paths, stats, usage):
        answers.update(found)
    return answers, stats


def with_decisions(chunks, result_paths) -> tuple[list[dict], Counter]:
    """Части для скептика: записи + ответ первого прохода. Части без ответа не идут дальше."""
    answers, stats = _answers(result_paths)
    rows = [{**row, "decisions": answers[row["k"]]["items"]} for row in chunks if row["k"] in answers]
    stats["частей без ответа"] = len(chunks) - len(rows)
    return rows, stats


def collect_inn(chunks, result_paths) -> tuple[list[dict], Counter, list[tuple]]:
    """Ответы скептика → (файл записи, статистика, замечания). Нет ответа или не fixed — запись не трогаем."""
    answers, stats = _answers(result_paths)
    updates, notes = [], []
    for chunk in chunks:
        source = {row["id"]: row for row in chunk["items"]}
        for row in (answers.get(chunk["k"]) or {}).get("items", []):
            item = source.get(row["id"])
            if not item or item["tr"] != row["tr"]:
                stats["чужая запись"] += 1
                continue
            stats[row["status"]] += 1
            if row["status"] != "fixed":
                continue
            ru, en = row["ru"].strip(), row["en"].strip()
            if ru == item["ru"] and en == item["en"]:
                stats["без изменений"] += 1
            elif item["tr"] in INN_KEEP:
                stats["оставлено решением владельца"] += 1
            elif not ru or not en:
                stats["пусто"] += 1
            elif _LATIN.search(_LATIN_ALLOWED_IN_RU.sub("", ru)):
                stats["латиница в RU"] += 1
                notes.append(("латиница", item["tr"], ru))
            elif _CYRILLIC.search(en):
                stats["кириллица в EN"] += 1
                notes.append(("кириллица", item["tr"], en))
            else:
                old_title, new_title = title_inn(item["ru"]), title_inn(ru)
                if "(" not in old_title and len(old_title) <= _INN_TITLE_MAX and (
                    "(" in new_title or len(new_title) > _INN_TITLE_MAX
                ):
                    stats["в названии пропадёт вещество"] += 1
                    notes.append(("название", item["tr"], item["ru"], ru))
                updates.append({"id": row["id"], "tr": item["tr"], "ru_old": item["ru"], "en_old": item["en"],
                                "ru_new": ru, "en_new": en, "products": item["products"]})
    return updates, stats, notes


def plan_inn_updates(updates) -> tuple[list[tuple], Counter]:
    records = AITranslationMemory.objects.in_bulk([update["id"] for update in updates])
    rows, stats = [], Counter()
    for update in updates:
        record = records.get(update["id"])
        if not record or record.namespace != INN_NAMESPACE or record.source_text != update["tr"]:
            stats["нет записи"] += 1
        elif record.ru_text != update["ru_old"] or record.en_text != update["en_old"]:
            stats["запись изменилась"] += 1
        else:
            rows.append((record, update))
            stats["к записи"] += 1
    return rows, stats


def apply_inn_updates(rows) -> int:
    """Запись словаря и один разнос по переводам товаров → сколько строк переводов обновлено."""
    with transaction.atomic():
        for record, update in rows:
            record.ru_text, record.en_text = update["ru_new"], update["en_new"]
            record.save(update_fields=["ru_text", "en_text", "updated_at"])
    return propagate_inn_translations({record.source_text for record, _ in rows})


def export_brands(include_known=False) -> list[dict]:
    """Бренды абзацев лекарств с примерами названий. По умолчанию — те, которых нет в словаре."""
    groups = defaultdict(lambda: {"count": 0, "names": Counter(), "inn": Counter(), "atc": Counter()})
    for product, item in _medicine_items():
        name = medicine_source_name(product.name, product.external_data)[0]
        brand = paragraph_brand(name, item.active_ingredient)
        if not brand:
            continue
        group = groups[brand]
        group["count"] += 1
        group["names"][name] += 1
        if item.active_ingredient:
            group["inn"][item.active_ingredient[:80]] += 1
        if item.atc_code:
            group["atc"][item.atc_code.strip().upper()] += 1
    known = set() if include_known else set(
        AITranslationMemory.objects.filter(namespace=BRAND_NAMESPACE).values_list("source_hash", flat=True)
    )
    return [
        {"brand": brand, "count": group["count"], "names": [value for value, _ in group["names"].most_common(3)],
         "inn": [value for value, _ in group["inn"].most_common(3)],
         "atc": [value for value, _ in group["atc"].most_common(3)]}
        for brand, group in groups.items()
        if source_hash(brand) not in known
    ]


def brand_chunks(export, size=BRAND_CHUNK_SIZE) -> list[dict]:
    rows = [{"i": index, **row} for index, row in
            enumerate(sorted(export, key=lambda row: (-row["count"], row["brand"])), 1)]
    return [{"k": start // size, "items": rows[start:start + size]} for start in range(0, len(rows), size)]


def latin_reading(brand: str, ru: str):
    """Чтение латиницы вместо турецкого: «дж» на месте C → ц или к, лишнее конечное «е». None — не исправить.

    Покупатели читают упаковку: в запросах Вордстата «крестор», «канестен», «клеоцин» и ни одного
    написания с «дж»; конечную E не читают («дермовейт», «отривин»; исключение — «никоретте»).
    """
    latin_words, cyrillic_words = brand.split(), ru.split()
    if len(latin_words) != len(cyrillic_words):
        return ru if "дж" not in ru.lower() else None
    fixed = []
    for latin, cyrillic in zip(latin_words, cyrillic_words):
        upper = latin.upper()
        letters = [match.start() for match in re.finditer(r"C(?!H)", upper)]
        pairs = [match.start() for match in re.finditer(r"дж", cyrillic, re.I)]
        if pairs and "J" not in upper:
            if len(letters) != len(pairs):  # «FUCITEC» → «Фуджитек»: «дж» только у C перед гласной
                letters = [match.start() for match in re.finditer(r"C(?=[AEIOUY])", upper)]
            if len(letters) != len(pairs):
                return None
            parts, last = [], 0
            for letter, pair in zip(letters, pairs):
                replacement = "ц" if upper[letter + 1:letter + 2] in ("E", "I", "Y") else "к"
                if cyrillic[pair].isupper():
                    replacement = replacement.upper()
                parts.append(cyrillic[last:pair] + replacement)
                last = pair + 2
            cyrillic = "".join(parts) + cyrillic[last:]
        if (
            re.search(r"[^AEIOUY]E$", upper)
            and not upper.endswith("TTE")
            and re.search(r"[бвгдзклмнпрстфхцчшщ]е$", cyrillic)
        ):
            cyrillic = cyrillic[:-1]
        fixed.append(cyrillic)
    return " ".join(fixed)


def collect_brands(chunks, result_paths) -> tuple[dict[str, str], Counter, list[tuple]]:
    """Ответы скептика → ({бренд: кириллица}, статистика, отсев). Аббревиатуры остаются латиницей."""
    answers, stats = _answers(result_paths)
    brands, dropped = {}, []
    for chunk in chunks:
        answered = {row["i"]: row for row in (answers.get(chunk["k"]) or {}).get("items", [])}
        for item in chunk["items"]:
            row = answered.get(item["i"])
            ru = ((row or {}).get("ru") or "").strip()
            if not row or row["brand"] != item["brand"]:
                stats["нет ответа или чужой бренд"] += 1
                continue
            if row["kind"] != "established":
                fixed = latin_reading(item["brand"], ru)
                if fixed is None:
                    stats["не удалось исправить «дж»"] += 1
                    dropped.append((item["brand"], ru))
                    continue
                stats["исправлено чтение"] += fixed != ru
                ru = fixed
            if not _CYRILLIC.search(ru):
                stats["без кириллицы"] += 1
            elif _BRAND_FORM.search(ru):
                stats["форма или доза в ru"] += 1
                dropped.append((item["brand"], ru))
            else:
                brands[item["brand"]] = ru
                stats["годен"] += 1
    return brands, stats, dropped


def new_brands(brands: dict[str, str]) -> dict[str, dict[str, str]]:
    """Только новые ключи: remember не перезаписывает, правка готового бренда — в админке."""
    known = set(
        AITranslationMemory.objects.filter(namespace=BRAND_NAMESPACE, source_hash__in=[source_hash(b) for b in brands])
        .values_list("source_hash", flat=True)
    )
    return {brand: {"ru": ru, "en": brand} for brand, ru in brands.items() if source_hash(brand) not in known}


def apply_brands(new: dict[str, dict[str, str]]) -> int:
    return remember(BRAND_NAMESPACE, new)
