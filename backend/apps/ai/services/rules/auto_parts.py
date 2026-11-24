"""Карточка автозапчасти кодом: название, описание и SEO без обращения к моделям.

Факты — из записи автозапчасти и её таблиц: вид детали (словарь ``auto_part_vocab``),
бренд, артикул, OEM-номера (``AutoPartNumber``), применимость (``AutoPartFitment``),
числовые характеристики источника. Результат — в форме ``LLMClient.generate_content``,
как у ``run_rule_content``: сохранение, модерация и применение идут общим путём.

Шаблоны (docs/AUTO_PARTS_AI_DESIGN.md, §3):

- RU: «{Вид} {Бренд} {артикул} для {марка модель}» — «Тормозные колодки Delphi LP2110
  для Volkswagen, Audi, Seat»;
- EN: «{Brand} {part number} {Kind} for {make model}».

Хвост применимости: одна марка и до трёх моделей — «для Nissan X-Trail»; одна марка и
больше моделей — «для Nissan»; до трёх марок — их список; больше — без хвоста (полный
список автомобилей — в таблице применимости).
"""

from __future__ import annotations

import time
from typing import Any

from apps.ai.services.rules.auto_part_vocab import find_kind, model_name, proper_name, translate_spec
from apps.ai.services.rules.text import truncate_at_word

TITLE_MAX = 255
META_TITLE_MAX = 80
META_DESCRIPTION_MAX = 200
MAX_TAIL_ITEMS = 3
DESCRIPTION_MAKES = 12
DESCRIPTION_NUMBERS = 20


class AutoPartKindUnknown(ValueError):
    """Вида детали нет в словаре — название не выдумываем."""


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]


def _fitment_tail(fitments: list[tuple[str, str]], locale: str) -> str:
    """«Nissan X-Trail», «Volkswagen, Audi, Seat» или пусто (марок больше трёх)."""
    makes = list(dict.fromkeys(make for make, _ in fitments if make))
    if not makes or len(makes) > MAX_TAIL_ITEMS:
        return ""
    if len(makes) > 1:
        return ", ".join(proper_name(make) for make in makes)
    models = list(dict.fromkeys(model for _, model in fitments if model))
    make = proper_name(makes[0])
    if not models or len(models) > MAX_TAIL_ITEMS:
        return make
    return f"{make} " + ", ".join(model_name(model, locale) for model in models)


def collect_auto_part_facts(product) -> dict[str, Any]:
    """Факты карточки из записи автозапчасти; ``AutoPartKindUnknown`` — вида нет в словаре."""
    from apps.catalog.models import AutoPartProduct

    part = AutoPartProduct.objects.filter(base_product_id=product.pk).select_related("brand").first()
    if part is None:
        raise ValueError("У товара нет записи автозапчасти")
    attrs = (part.external_data or {}).get("attributes") or {}
    crumbs = [str(title) for title in attrs.get("aloparca_breadcrumbs") or []]
    # Вид карточки («Fren Disk Balata»), затем разделы источника от точного к общему;
    # первые два уровня крошек — «Oto Yedek Parça → Yedek Parça».
    candidates = [attrs.get("part_kind_tr"), *reversed(crumbs[3:])]
    kind = find_kind(*candidates)
    if kind is None:
        raise AutoPartKindUnknown(
            "Вида детали нет в словаре автозапчастей: "
            f"«{attrs.get('part_kind_tr') or part.name}» — добавьте его в auto_part_vocab.PART_KINDS"
        )
    part_number = (part.part_number or str(attrs.get("part_number") or "")).strip()
    if not part_number:
        raise ValueError("У автозапчасти нет артикула")
    fitments = list(part.fitments.order_by("pk").values_list("make", "model"))
    numbers = list(part.numbers.filter(kind="oem").order_by("pk").values_list("number", flat=True))
    specs = [row for row in (translate_spec(k, v) for k, v in (attrs.get("specs") or {}).items()) if row]
    return {
        "kind_ru": kind[0],
        "kind_en": kind[1],
        "brand": proper_name(part.brand.name) if part.brand_id and part.brand.slug != "other" else "",
        "part_number": part_number,
        "tail": {locale: _fitment_tail(fitments, locale) for locale in ("ru", "en")},
        "makes": [proper_name(make) for make in dict.fromkeys(make for make, _ in fitments if make)],
        "fitment_count": len(fitments),
        "numbers": numbers,
        "specs": specs,
    }


def build_auto_part_titles(facts: dict[str, Any]) -> dict[str, str]:
    identity = " ".join(part for part in (facts["brand"], facts["part_number"]) if part)
    ru = f"{_capitalize(facts['kind_ru'])} {identity}"
    en = f"{identity} {facts['kind_en']}"
    if facts["tail"]["ru"]:
        with_tail = (f"{ru} для {facts['tail']['ru']}", f"{en} for {facts['tail']['en']}")
        if all(len(title) <= TITLE_MAX for title in with_tail):
            ru, en = with_tail
    return {"ru": ru[:TITLE_MAX], "en": en[:TITLE_MAX]}


def build_auto_part_descriptions(facts: dict[str, Any]) -> dict[str, str]:
    """Описание из фактов: что это, к чему подходит, OEM-номера, размеры."""
    identity = " ".join(part for part in (facts["brand"], facts["part_number"]) if part)
    makes = facts["makes"]
    shown_makes = ", ".join(makes[:DESCRIPTION_MAKES])
    more_ru = f" и ещё {len(makes) - DESCRIPTION_MAKES}" if len(makes) > DESCRIPTION_MAKES else ""
    more_en = f" and {len(makes) - DESCRIPTION_MAKES} more" if len(makes) > DESCRIPTION_MAKES else ""
    numbers = facts["numbers"]
    shown_numbers = ", ".join(numbers[:DESCRIPTION_NUMBERS])
    ru = [f"<p>{_capitalize(facts['kind_ru'])} {identity} — новая запчасть из Турции. Артикул производителя: {facts['part_number']}.</p>"]
    en = [f"<p>{identity} {facts['kind_en']} — a new part from Turkey. Manufacturer part number: {facts['part_number']}.</p>"]
    if makes:
        ru.append(
            f"<p>Подходит для автомобилей {shown_makes}{more_ru}. Вариантов кузова и двигателя в списке "
            f"применимости: {facts['fitment_count']}. Перед заказом сверьте деталь по OEM-номеру или "
            "по VIN автомобиля.</p>"
        )
        en.append(
            f"<p>Fits {shown_makes}{more_en}. Body and engine versions in the fitment list: "
            f"{facts['fitment_count']}. Please check the part by OEM number or VIN before ordering.</p>"
        )
    if numbers:
        tail_ru = f" и ещё {len(numbers) - DESCRIPTION_NUMBERS}" if len(numbers) > DESCRIPTION_NUMBERS else ""
        tail_en = f" and {len(numbers) - DESCRIPTION_NUMBERS} more" if len(numbers) > DESCRIPTION_NUMBERS else ""
        ru.append(f"<p>OEM-номера: {shown_numbers}{tail_ru}.</p>")
        en.append(f"<p>OEM numbers: {shown_numbers}{tail_en}.</p>")
    if facts["specs"]:
        ru.append("<ul>" + "".join(f"<li>{row[0]}</li>" for row in facts["specs"]) + "</ul>")
        en.append("<ul>" + "".join(f"<li>{row[1]}</li>" for row in facts["specs"]) + "</ul>")
    return {"ru": "".join(ru), "en": "".join(en)}


def _meta_title(title: str, base: str, long_tail: str, short_tail: str) -> str:
    for candidate in (f"{title} — {long_tail}", f"{base} — {long_tail}", f"{base} — {short_tail}", base):
        if len(candidate) <= META_TITLE_MAX:
            return candidate
    return truncate_at_word(base, META_TITLE_MAX)


def build_auto_part_seo(facts: dict[str, Any], titles: dict[str, str]) -> dict[str, dict[str, Any]]:
    identity = " ".join(part for part in (facts["brand"], facts["part_number"]) if part)
    base = {"ru": f"{_capitalize(facts['kind_ru'])} {identity}", "en": f"{identity} {facts['kind_en']}"}
    oem = ", ".join(facts["numbers"][:5])
    fits_ru = f" Подходит для {facts['tail']['ru'] or ', '.join(facts['makes'][:5])}." if facts["makes"] else ""
    fits_en = f" Fits {facts['tail']['en'] or ', '.join(facts['makes'][:5])}." if facts["makes"] else ""
    description = {
        "ru": f"{base['ru']}.{fits_ru}{' OEM: ' + oem + '.' if oem else ''} Заказ из Турции через менеджера, доставка 7–14 дней.",
        "en": f"{base['en']}.{fits_en}{' OEM: ' + oem + '.' if oem else ''} Order from Turkey via a manager, delivery in 7–14 days.",
    }
    keywords = {
        "ru": [base["ru"], facts["kind_ru"], facts["part_number"], *facts["numbers"][:5],
               *(f"{facts['kind_ru']} {make}" for make in facts["makes"][:3]), f"{facts['kind_ru']} из Турции"],
        "en": [base["en"], facts["kind_en"].lower(), facts["part_number"], *facts["numbers"][:5],
               *(f"{facts['kind_en'].lower()} {make}" for make in facts["makes"][:3]), f"{facts['kind_en'].lower()} from Turkey"],
    }
    tails = {"ru": ("купить из Турции", "из Турции"), "en": ("buy from Turkey", "from Turkey")}
    return {
        locale: {
            "seo_title": _meta_title(titles[locale], base[locale], *tails[locale]),
            "seo_description": truncate_at_word(description[locale], META_DESCRIPTION_MAX),
            "keywords": list(dict.fromkeys(word for word in keywords[locale] if word))[:10],
        }
        for locale in ("ru", "en")
    }


def run_auto_part_content(product) -> dict[str, Any]:
    """Результат обработки автозапчасти: всё собрано кодом, модель не вызывается."""
    started = time.time()
    facts = collect_auto_part_facts(product)
    titles = build_auto_part_titles(facts)
    descriptions = build_auto_part_descriptions(facts)
    seo = build_auto_part_seo(facts, titles)
    content: dict[str, Any] = {
        locale: {
            "generated_title": titles[locale],
            "generated_description": descriptions[locale],
            **seo[locale],
        }
        for locale in ("ru", "en")
    }
    content["attributes"] = {"dynamic_attributes": []}
    return {
        "tokens": {"prompt": 0, "completion": 0, "total": 0, "cached": 0},
        "cost_usd": 0.0,
        "content": content,
        "processing_time_ms": int((time.time() - started) * 1000),
        "rule_content": {
            "description_source": "template",
            "title_sources": {"ru": "rules", "en": "rules"},
            "llm_called": False,
            "facts": {**facts, "specs": [row[0] for row in facts["specs"]]},
        },
    }
