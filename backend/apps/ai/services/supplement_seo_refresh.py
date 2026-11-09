"""Пересборка SEO БАДов кодом из готовых AI-логов, без модели (SEO-ядро 07.11.2026, ревью #333).

SEO БАДа (title, description, keywords) собирает ``supplement_content.build_seo`` из частей названия:
бренд, бренд кириллицей, «что это», фасовка. Эти части лежат в логе обработки
(``raw_llm_response.rule_content.supplement``), поэтому новый шаблон можно применить ко всем БАДам
без запросов к модели. Название (H1, ``name``) не меняется.

- Входные данные — лог, по которому собрано название на сайте (круг описаний БАДов возвращает
  прежние название и SEO). Если название из частей лога не собирается в текущее (модератор поправил
  название в логе или на карточке), товар пропускается: части лога — исходный ответ модели.
- Объект (домен, перевод) перезаписывается, только если все его SEO-поля пусты, уже как в коде или
  записаны какой-либо обработкой товара; хоть одно поле правлено вручную — объект остаётся целиком.
- «Инструкция на русском» — по текущему описанию на сайте.
- Работа идёт пачками: каждая пачка читается и пишется в одной транзакции под блокировкой строк,
  пишутся только SEO-поля через ``update()`` — без ``save()`` и синхронизации домена с ``Product``,
  чтобы не откатить цену, остаток и описание, записанные парсером тем временем.
- Бэкап — только SEO-поля строк и SEO лога (jsonl), возврат — ``restore_backup``.

Где лежит SEO БАДа: ``SupplementProduct`` (EN, как пишет применение лога) и его копия в ``Product``
(как делает синхронизация домена), переводы ``SupplementProductTranslation`` и ``ProductTranslation``.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, TextIO

from django.apps import apps
from django.db import transaction
from django.db.models.fields.json import KeyTransform
from django.utils import timezone

from apps.ai.services import supplement_content
from apps.ai.services.medicine_refresh import _keywords_text
from apps.catalog.services.delivery_terms import replace_terms

BATCH_SIZE = 200
SEO_FIELDS = ("meta_title", "og_title", "meta_description", "og_description", "meta_keywords")
PRODUCT_SEO_FIELDS = (
    "seo_title", "seo_description", "keywords", "meta_title", "meta_description", "meta_keywords", "og_title",
    "og_description",
)
LOG_LABEL = "ai.aiprocessinglog"
DOMAIN_LABEL = "catalog.supplementproduct"
PRODUCT_LABEL = "catalog.product"
_REBUILT_KEY = "supplement_seo_rebuilt_at"
# Что записала пересборка: отдельно от seo_translations лога. Прежняя версия команды переписывала
# seo_translations обеих локалей, даже когда часть объектов оставалась, — и пропадало доказательство,
# что их SEO записано обработкой (7540, 7694, 7377 после прогонов 07.11.2026).
_REBUILT_SEO_KEY = "supplement_seo_rebuilt"
# Чем применение лога заполняет поле, если в seo_translations его нет (ContentGenerator.apply_log_to_product).
_COUNTERPART = {"og_title": "meta_title", "og_description": "meta_description"}
_GENERATED = {
    "meta_title": "generated_seo_title", "og_title": "generated_seo_title",
    "meta_description": "generated_seo_description", "og_description": "generated_seo_description",
    "meta_keywords": "generated_keywords",
}
_LINE_NUMBER_RE = re.compile(r"\d[\d/.,]*\+?")
# Разовые правки SEO БАДов прямо в базе, мимо логов (флаг ``legacy_as_auto``). 28.10.2026 по решению
# владельца (Merchant Center) срок доставки заменён bulk_update в Product, SupplementProduct и переводах
# (бэкап ~/ai-pilot/out/supp-721-backup.json), а в логах остался прежний — без этой замены такое SEO
# похоже на ручную правку (07.11.2026: 5 333 объекта остались со старым шаблоном).
LEGACY_EDITS = (
    ("доставка 7–21 рабочий день", "доставка 7–14 дней"),
    ("delivery in 7–21 business days", "delivery in 7–14 days"),
)
# 09.11.2026 срок БАДов снова заменён в базе (команда replace_delivery_terms, ``delivery_terms``) —
# «авиа 3–7, наземная 7–14, морем 20–45 дней»; в логах остался прежний.
# Следы правки SEO в истории админки (LogEntry): поля SEO и названия их полей в форме.
_ADMIN_SEO_RE = re.compile(r"meta|\bog[ _]|seo|мета", re.IGNORECASE)


def seo_translations_with_rebuilt(attrs: Any) -> dict:
    """SEO лога с тем, что записала пересборка (``supplement_seo_rebuilt``) поверх: на карточке именно оно.

    Нужно повторному применению лога и модерации — иначе они вернут или покажут как «предложенное»
    прежнее SEO лога (ревью #335).
    """
    attrs = attrs if isinstance(attrs, dict) else {}
    seo = {
        locale: dict(values) for locale, values in (attrs.get("seo_translations") or {}).items()
        if isinstance(values, dict)
    }
    rebuilt = attrs.get(_REBUILT_SEO_KEY)
    for locale, values in (rebuilt.items() if isinstance(rebuilt, dict) else ()):
        if isinstance(values, dict):
            seo[locale] = {**seo.get(locale, {}), **values}
    return seo


def _model(label: str):
    return apps.get_model(label)


def title_brand(brand: str, name: str, product_ru: str) -> str:
    """Бренд названия: к бренду лога код мог добавить число линейки или ступень смеси
    («HIPP» → «HIPP 2 …», ``_restore_lost_numbers``) — оно видно в названии."""
    if not brand or not name.startswith(brand):
        return brand
    rest = name[len(brand):].split()
    first = rest[0].rstrip(",") if rest else ""
    if first and _LINE_NUMBER_RE.fullmatch(first) and not product_ru.startswith(first):
        return f"{brand} {first}"
    return brand


# ── Чтение пачки ─────────────────────────────────────────────────────────────


@dataclass
class _Batch:
    names: dict[int, tuple[str, str]] = field(default_factory=dict)  # product_id → (H1, описание RU)
    targets: dict[int, list[tuple[str, int, str, dict]]] = field(default_factory=dict)  # (модель, pk, локаль, SEO)
    domains: dict[int, int] = field(default_factory=dict)  # product_id → pk домена
    logs: dict[int, list[dict]] = field(default_factory=dict)
    admin_seo_edits: set[int] = field(default_factory=set)  # product_id с правкой SEO в админке


def _load(product_ids: list[int], lock: bool, admin_history: bool = False) -> _Batch:
    Product = _model(PRODUCT_LABEL)
    Domain = _model(DOMAIN_LABEL)
    DomainTr = _model("catalog.supplementproducttranslation")
    ProductTr = _model("catalog.producttranslation")
    Log = _model(LOG_LABEL)

    def query(model, **filters):
        qs = model.objects.filter(**filters)
        return qs.select_for_update() if lock else qs

    batch = _Batch()
    products = {row["id"]: row for row in query(Product, id__in=product_ids).values("id", "name", "description")}
    domains = list(query(Domain, base_product_id__in=product_ids).values("id", "base_product_id", "name", "description", *SEO_FIELDS))
    domain_by_pk = {row["id"]: row for row in domains}
    domain_tr = list(
        query(DomainTr, product_id__in=list(domain_by_pk), locale__in=("ru", "en"))
        .values("id", "product_id", "locale", "name", "description", *SEO_FIELDS)
    )
    product_tr = list(
        query(ProductTr, product_id__in=product_ids, locale__in=("ru", "en")).values("id", "product_id", "locale", *SEO_FIELDS)
    )
    ru_tr = {row["product_id"]: row for row in domain_tr if row["locale"] == "ru"}
    for row in domains:
        pid = row["base_product_id"]
        batch.domains[pid] = row["id"]
        tr = ru_tr.get(row["id"]) or {}
        product = products.get(pid) or {}
        batch.names[pid] = (
            (tr.get("name") or row["name"] or product.get("name") or "").strip(),
            tr.get("description") or row["description"] or product.get("description") or "",
        )
        batch.targets[pid] = [(DOMAIN_LABEL, row["id"], "en", {f: row[f] for f in SEO_FIELDS})]
    for row in domain_tr:
        pid = domain_by_pk[row["product_id"]]["base_product_id"]
        batch.targets[pid].append(("catalog.supplementproducttranslation", row["id"], row["locale"], {f: row[f] for f in SEO_FIELDS}))
    for row in product_tr:
        if row["product_id"] in batch.targets:
            batch.targets[row["product_id"]].append(("catalog.producttranslation", row["id"], row["locale"], {f: row[f] for f in SEO_FIELDS}))
    # Из лога — только части названия и SEO, без raw_llm_response целиком.
    log_rows = (
        Log.objects.filter(product_id__in=list(batch.domains))
        .annotate(
            supplement=KeyTransform("supplement", KeyTransform("rule_content", "raw_llm_response")),
            seo=KeyTransform("seo_translations", "extracted_attributes"),
            rebuilt=KeyTransform(_REBUILT_SEO_KEY, "extracted_attributes"),
        )
        .values(
            "id", "product_id", "generated_title", "generated_seo_title", "generated_seo_description",
            "generated_keywords", "supplement", "seo", "rebuilt",
        )
        .order_by("-id")
    )
    for row in log_rows:
        row["supplement"] = row["supplement"] if isinstance(row["supplement"], dict) else {}
        row["seo"] = row["seo"] if isinstance(row["seo"], dict) else {}
        row["rebuilt"] = row["rebuilt"] if isinstance(row["rebuilt"], dict) else {}
        batch.logs.setdefault(row["product_id"], []).append(row)
    if admin_history:
        batch.admin_seo_edits = _admin_seo_edits(batch, {pk: pid for pid, pk in batch.domains.items()}, domain_tr, product_tr)
    return batch


def _admin_seo_edits(batch: _Batch, domain_to_product: dict, domain_tr: list[dict], product_tr: list[dict]) -> set[int]:
    """Товары, у которых в истории админки есть правка SEO: домена (вместе с переводами в инлайнах),
    перевода, товара. Такой товар считается правленым вручную целиком."""
    from django.contrib.admin.models import CHANGE, LogEntry
    from django.contrib.contenttypes.models import ContentType

    owners: dict[tuple[int, str], int] = {}
    for label, rows in (
        (DOMAIN_LABEL, [(pk, pid) for pk, pid in domain_to_product.items()]),
        (PRODUCT_LABEL, [(pid, pid) for pid in batch.domains]),
        ("catalog.supplementproducttranslation", [(r["id"], domain_to_product[r["product_id"]]) for r in domain_tr]),
        ("catalog.producttranslation", [(r["id"], r["product_id"]) for r in product_tr if r["product_id"] in batch.domains]),
    ):
        content_type = ContentType.objects.get_for_model(_model(label))
        for pk, pid in rows:
            owners[(content_type.id, str(pk))] = pid
    if not owners:
        return set()
    entries = LogEntry.objects.filter(
        action_flag=CHANGE,
        content_type_id__in={key[0] for key in owners},
        object_id__in={key[1] for key in owners},
    ).values_list("content_type_id", "object_id", "change_message")
    return {
        owners[(content_type_id, object_id)]
        for content_type_id, object_id, message in entries
        if (content_type_id, object_id) in owners and _ADMIN_SEO_RE.search(str(message or ""))
    }


# ── План ─────────────────────────────────────────────────────────────────────


@dataclass
class ObjectChange:
    label: str
    pk: int
    locale: str
    old: dict[str, Optional[str]]  # как в базе, байт в байт: restore возвращает его без изменений
    new: dict[str, str]


@dataclass
class ProductPlan:
    product_id: int
    reason: str = ""
    log_id: Optional[int] = None
    domain_pk: Optional[int] = None
    new: dict = field(default_factory=dict)
    changes: list[ObjectChange] = field(default_factory=list)
    kept_manual: int = 0
    # (модель, локаль, поле, значение) — почему объект оставлен: для показа
    manual_fields: list[tuple[str, str, str, str]] = field(default_factory=list)


def _logged_name(log: dict) -> str:
    seo_ru = log["seo"].get("ru") if isinstance(log["seo"].get("ru"), dict) else {}
    return str(seo_ru.get("generated_title") or log["generated_title"] or "").strip()


def _with_legacy_edits(value: str) -> str:
    for old, new in LEGACY_EDITS:
        value = value.replace(old, new)
    return value


def _legacy_variants(value: str) -> set[str]:
    """Значение лога после разовых правок в базе: 28.10 (7–14 дней) и 09.11 (``replace_delivery_terms``)."""
    edited = _with_legacy_edits(value)
    return {edited, replace_terms(value, supplements=True), replace_terms(edited, supplements=True)}


def _candidates(
    logs: list[dict], locale: str, name: str, legacy_as_auto: bool = False, legacy_code: Optional[dict] = None
) -> set[str]:
    """Что могла записать в поле какая-либо обработка товара или пересборка; с ``legacy_as_auto`` — ещё
    разовые правки в базе и вывод прежнего кода из тех же частей лога (``legacy_code``)."""
    values = set()
    for log in logs:
        for source in (log["seo"], log["rebuilt"]):
            seo = source.get(locale) if isinstance(source.get(locale), dict) else {}
            for key in (name, _COUNTERPART.get(name)):
                if key:
                    values.add(_keywords_text(seo.get(key)) if key == "meta_keywords" else str(seo.get(key) or "").strip())
        values.add(_keywords_text(log[_GENERATED[name]]) if name == "meta_keywords" else str(log[_GENERATED[name]] or "").strip())
    if legacy_as_auto:
        values |= set((legacy_code or {}).get(locale, {}).get(name, ()))
    values.discard("")
    if legacy_as_auto:
        values |= {variant for value in values for variant in _legacy_variants(value)}
    return values


# ── Прежний код (до SEO-ядра, PR #333) ───────────────────────────────────────
# Копия build_seo до c61cb9d7 — только для распознавания: SEO, которое он собрал из тех же частей лога,
# записано кодом, а не вручную, даже если запись об этом в логе не сохранилась.
_LEGACY_TEXTS = {
    "ru": {
        "buy": " — купить из Турции", "turkey": " из Турции", "info": "Описание и состав на русском.",
        "keyword_turkey": "{brand} из Турции", "keyword_buy": "{brand} купить", "supplement": "БАД",
        "baby": "детское питание",
    },
    "en": {
        "buy": " — buy from Turkey", "turkey": " from Turkey", "info": "Description and ingredients in English.",
        "keyword_turkey": "{brand} Turkey", "keyword_buy": "buy {brand}", "supplement": "food supplement",
        "baby": "baby food",
    },
}
_LEGACY_ORDERS = {
    "ru": ("Заявка менеджеру, доставка 7–21 рабочий день.", "Заявка менеджеру, доставка 7–14 дней."),
    "en": ("Send a request, delivery in 7–21 business days.", "Send a request, delivery in 7–14 days."),
}


def legacy_seo(brand: str, brand_ru: str, product: dict, pack: Any, baby_food: bool = False) -> dict[str, dict]:
    """{локаль: {поле: {значения}}} — что собрал бы прежний build_seo (оба срока доставки)."""
    sc = supplement_content
    result: dict[str, dict] = {}
    for locale in ("ru", "en"):
        texts = dict(_LEGACY_TEXTS[locale])
        if baby_food:
            texts["supplement"] = texts["baby"]
        core = str(product.get(locale) or "").strip()
        pack_text = getattr(pack, locale, "") if pack else ""
        cyrillic = brand_ru if locale == "ru" and brand_ru and brand_ru.lower() != brand.lower() else ""
        short = core.split(", ")[0]
        heads = [f"{cyrillic} ({brand})", brand] if cyrillic else [brand]
        names = [sc.assemble_title(head, core, "", locale) for head in heads]
        candidates = []
        first = re.split(r" (?:и|с|со|and|with) ", short)[0]
        for head, name in zip(heads, names):
            if pack_text:
                candidates.append(f"{name}, {pack_text}{texts['buy']}")
            candidates += [name + texts["buy"], name + texts["turkey"]]
            for part in dict.fromkeys((short, first)):
                part_name = sc.assemble_title(head, part, "", locale)
                candidates += [part_name + texts["buy"], part_name + texts["turkey"]]
        candidates += names
        title = next((c for c in candidates if len(c) <= sc.SEO_TITLE_MAX), None) or sc._fit(names[-1], sc.SEO_TITLE_MAX)
        leads = []
        for name in names:
            leads += [f"{name}, {pack_text}{texts['turkey']}." if pack_text else f"{name}{texts['turkey']}.", f"{name}{texts['turkey']}."]
        lead = next((c for c in leads if len(c) <= sc.SEO_DESCRIPTION_MAX), None) or sc._fit(leads[-1], sc.SEO_DESCRIPTION_MAX - 1) + "."
        descriptions = set()
        for order in _LEGACY_ORDERS[locale]:
            description = lead
            for sentence in (texts["info"], order):
                if len(description) + 1 + len(sentence) <= sc.SEO_DESCRIPTION_MAX:
                    description = f"{description} {sentence}"
            descriptions.add(description)
        core_keyword = short if locale == "en" else short[:1].lower() + short[1:]
        specific = bool(short) and not sc.is_generic(short, locale)
        shown = cyrillic or brand
        keywords = [
            brand, cyrillic, f"{shown} {core_keyword}" if specific else "", core_keyword if specific else "",
            texts["keyword_turkey"].format(brand=shown), texts["keyword_buy"].format(brand=shown),
            f"{texts['supplement']} {core_keyword}" if specific else texts["supplement"],
        ]
        result[locale] = {
            "meta_title": {title}, "og_title": {title},
            "meta_description": descriptions, "og_description": descriptions,
            "meta_keywords": {", ".join(list(dict.fromkeys(k for k in keywords if k))[:8])},
        }
    return result


def _parts(data: dict, name: str) -> Optional[tuple]:
    """(бренд названия, бренд кириллицей, «что это», фасовка, детское питание) из части лога."""
    product_text = data.get("product") if isinstance(data.get("product"), dict) else {}
    if not product_text.get("ru"):
        return None
    pack_data = data.get("pack") if isinstance(data.get("pack"), dict) else {}
    pack_ru, pack_en = str(pack_data.get("ru") or ""), str(pack_data.get("en") or "")
    pack = type("Pack", (), {"ru": pack_ru, "en": pack_en})() if pack_ru or pack_en else None
    brand = title_brand(str(data.get("brand") or ""), name, product_text["ru"])
    return brand, str(data.get("brand_ru") or ""), product_text, pack, bool(data.get("baby_food"))


def _new_values(data: dict, name: str, description: str) -> Optional[dict]:
    product_text = data.get("product") if isinstance(data.get("product"), dict) else {}
    if not product_text.get("ru"):
        return None
    pack_data = data.get("pack") if isinstance(data.get("pack"), dict) else {}
    pack_ru, pack_en = str(pack_data.get("ru") or ""), str(pack_data.get("en") or "")
    brand = title_brand(str(data.get("brand") or ""), name, product_text["ru"])
    # Части лога — исходный ответ модели; правку названия модератором они не знают (ревью #333).
    if supplement_content.assemble_title(brand, product_text["ru"], pack_ru, "ru") != name:
        return {}
    pack = type("Pack", (), {"ru": pack_ru, "en": pack_en})() if pack_ru or pack_en else None
    seo = supplement_content.build_seo(
        brand, str(data.get("brand_ru") or ""), product_text, pack,
        baby_food=bool(data.get("baby_food")), usage=supplement_content.has_usage_paragraph(description),
    )
    return {
        locale: {
            "meta_title": seo[locale]["seo_title"],
            "og_title": seo[locale]["seo_title"],
            "meta_description": seo[locale]["seo_description"],
            "og_description": seo[locale]["seo_description"],
            "meta_keywords": _keywords_text(seo[locale]["keywords"]),
        }
        for locale in ("ru", "en")
    }


def _plan(product_id: int, batch: _Batch, legacy_as_auto: bool = False) -> ProductPlan:
    plan = ProductPlan(product_id)
    if product_id not in batch.domains:
        plan.reason = "нет доменной записи БАДа"
        return plan
    name, description = batch.names[product_id]
    logs = batch.logs.get(product_id, [])
    source = next((log for log in logs if log["supplement"] and _logged_name(log) == name), None)
    if source is None:
        plan.reason = "название не из лога" if any(log["supplement"] for log in logs) else "нет лога кода БАДа"
        return plan
    new = _new_values(source["supplement"], name, description)
    if new is None:
        plan.reason = "в логе нет «что это»"
        return plan
    if not new:
        plan.reason = "название правлено"
        return plan
    plan.log_id, plan.domain_pk, plan.new = source["id"], batch.domains[product_id], new
    if product_id in batch.admin_seo_edits:
        plan.reason = "SEO правлено в админке"
        return plan
    # Прежний код из частей каждого лога этого названия: по ним SEO на сайте могло быть собрано раньше.
    legacy_code: dict = {}
    if legacy_as_auto:
        for log in logs:
            parts = _parts(log["supplement"], name) if log["supplement"] and _logged_name(log) == name else None
            if parts:
                for locale, fields in legacy_seo(*parts).items():
                    for key, values in fields.items():
                        legacy_code.setdefault(locale, {}).setdefault(key, set()).update(values)
    for label, pk, locale, current in batch.targets[product_id]:
        target = new[locale]
        old = {f: str(current[f] or "").strip() for f in SEO_FIELDS}  # только для сравнения
        if old == target:
            continue
        # Хоть одно поле правлено вручную — объект целиком остаётся (иначе og_title ≠ meta_title).
        manual = [
            f for f in SEO_FIELDS
            if old[f] and old[f] != target[f] and old[f] not in _candidates(logs, locale, f, legacy_as_auto, legacy_code)
        ]
        if manual:
            plan.kept_manual += 1
            plan.manual_fields += [(label, locale, f, old[f]) for f in manual]
            continue
        plan.changes.append(ObjectChange(label, pk, locale, {f: current[f] for f in SEO_FIELDS}, target))
    return plan


# ── Запись и бэкап ───────────────────────────────────────────────────────────


def _backup_rows(plan: ProductPlan, product_row: Optional[dict], log_row: dict) -> list[dict]:
    rows = [{"model": change.label, "pk": change.pk, "fields": change.old} for change in plan.changes]
    if product_row is not None:
        rows.append({"model": PRODUCT_LABEL, "pk": product_row["id"], "fields": {f: product_row[f] for f in PRODUCT_SEO_FIELDS}})
    attrs = log_row["extracted_attributes"] or {}
    rows.append({
        "model": LOG_LABEL, "pk": log_row["id"],
        "fields": {
            "seo_translations": attrs.get("seo_translations"),
            "generated_seo_title": log_row["generated_seo_title"],
            _REBUILT_KEY: attrs.get(_REBUILT_KEY),
            _REBUILT_SEO_KEY: attrs.get(_REBUILT_SEO_KEY),
        },
    })
    return rows


def _product_mirror(domain_seo: dict) -> dict:
    """Копия SEO домена в Product — как ``_sync_to_base_product``."""
    return {
        "seo_title": domain_seo["meta_title"],
        "seo_description": domain_seo["meta_description"],
        "keywords": [k.strip() for k in (domain_seo["meta_keywords"] or "").split(",") if k.strip()],
        "meta_title": domain_seo["meta_title"],
        "meta_description": domain_seo["meta_description"],
        "meta_keywords": domain_seo["meta_keywords"],
        "og_title": domain_seo["og_title"],
        "og_description": domain_seo["og_description"],
    }


def _write(plan: ProductPlan, backup: Optional[TextIO]) -> None:
    Product = _model(PRODUCT_LABEL)
    Log = _model(LOG_LABEL)
    log_row = Log.objects.select_for_update().filter(pk=plan.log_id).values("id", "extracted_attributes", "generated_seo_title").first()
    domain_change = next((c for c in plan.changes if c.label == DOMAIN_LABEL), None)
    product_row = (
        Product.objects.filter(pk=plan.product_id).values("id", *PRODUCT_SEO_FIELDS).first() if domain_change else None
    )
    if backup is not None:
        for row in _backup_rows(plan, product_row, log_row):
            backup.write(json.dumps(row, ensure_ascii=False) + "\n")
    for change in plan.changes:
        _model(change.label).objects.filter(pk=change.pk).update(**change.new)
    if domain_change is not None:
        Product.objects.filter(pk=plan.product_id).update(**_product_mirror(domain_change.new))
    # SEO лога не переписывается: оно — доказательство для объектов, оставленных как есть.
    attrs = dict(log_row["extracted_attributes"] or {})
    attrs[_REBUILT_SEO_KEY] = {locale: dict(plan.new[locale]) for locale in ("ru", "en")}
    attrs[_REBUILT_KEY] = timezone.now().isoformat()
    Log.objects.filter(pk=plan.log_id).update(extracted_attributes=attrs)
    _touch(plan.product_id, plan.domain_pk)


def _touch(product_id: Optional[int], domain_pk: Optional[int]) -> None:
    """update() не трогает auto_now ``updated_at``, а lastmod sitemap БАДов берётся из
    ``SupplementProduct.updated_at`` (SitemapProductsView): новое SEO должно попасть в sitemap."""
    now = timezone.now()
    if domain_pk:
        _model(DOMAIN_LABEL).objects.filter(pk=domain_pk).update(updated_at=now)
    if product_id:
        _model(PRODUCT_LABEL).objects.filter(pk=product_id).update(updated_at=now)


def _sync(handle: Optional[TextIO]) -> None:
    """Бэкап пачки — на диск до коммита пачки: после OOM/SIGKILL хвост записанной пачки не теряется."""
    if handle is not None:
        handle.flush()
        os.fsync(handle.fileno())


def run(
    product_ids: Iterable[int], *, apply: bool = False, backup: Optional[TextIO] = None, show: int = 10,
    stats: Optional[Counter] = None, legacy_as_auto: bool = False,
) -> tuple[Counter, list[ProductPlan]]:
    """План (и запись при ``apply``) пачками по ``BATCH_SIZE``; возвращает счётчики и до ``show`` примеров
    (изменения и объекты, оставленные как правленые вручную, с полями).

    ``legacy_as_auto`` — значения логов с разовыми правками ``LEGACY_EDITS`` тоже считаются записанными
    обработкой; товары с правкой SEO в истории админки (LogEntry) при этом пропускаются целиком.
    """
    if apply and backup is None:
        raise ValueError("запись только с бэкапом")
    stats = Counter() if stats is None else stats
    examples: list[ProductPlan] = []
    ids = list(product_ids)
    for start in range(0, len(ids), BATCH_SIZE):
        chunk = ids[start:start + BATCH_SIZE]
        with transaction.atomic():
            batch = _load(chunk, lock=apply, admin_history=legacy_as_auto)
            for product_id in chunk:
                plan = _plan(product_id, batch, legacy_as_auto)
                stats["товаров"] += 1
                if plan.reason:
                    stats[f"пропущено: {plan.reason}"] += 1
                    continue
                if plan.kept_manual:
                    stats["объектов правлено вручную (оставлены)"] += plan.kept_manual
                    if len(examples) < show:
                        examples.append(plan)
                if not plan.changes:
                    # Товар, у которого все отличия — «ручные», — не «уже как в коде» (07.11.2026: 7540 и др.).
                    stats["товаров: всё оставлено как правленое вручную" if plan.kept_manual else "уже как в коде"] += 1
                    continue
                stats["к изменению"] += 1
                stats["объектов"] += len(plan.changes)
                if len(examples) < show and plan not in examples:
                    examples.append(plan)
                if apply:
                    _write(plan, backup)
                    stats["записано"] += 1
            _sync(backup)
    return stats, examples


def restore_backup(path: str, snapshot_path: str) -> int:
    """Вернуть строки из бэкапа (только SEO-поля и SEO лога) пачками; текущие значения тех же строк —
    сначала в ``snapshot_path`` (новый файл: существующий не перезаписывается)."""
    with open(path) as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    restored = 0
    with open(snapshot_path, "x") as snapshot:
        for start in range(0, len(rows), BATCH_SIZE):
            with transaction.atomic():
                for row in rows[start:start + BATCH_SIZE]:
                    model = _model(row["model"])
                    if row["model"] == LOG_LABEL:
                        current = model.objects.select_for_update().filter(pk=row["pk"]).values(
                            "extracted_attributes", "generated_seo_title"
                        ).first()
                        if current is None:
                            continue
                        attrs = dict(current["extracted_attributes"] or {})
                        snapshot.write(json.dumps({"model": LOG_LABEL, "pk": row["pk"], "fields": {
                            "seo_translations": attrs.get("seo_translations"),
                            "generated_seo_title": current["generated_seo_title"],
                            _REBUILT_KEY: attrs.get(_REBUILT_KEY),
                            _REBUILT_SEO_KEY: attrs.get(_REBUILT_SEO_KEY),
                        }}, ensure_ascii=False) + "\n")
                        fields = row["fields"]
                        attrs["seo_translations"] = fields["seo_translations"]
                        for key in (_REBUILT_KEY, _REBUILT_SEO_KEY):
                            if fields.get(key):
                                attrs[key] = fields[key]
                            else:
                                attrs.pop(key, None)
                        model.objects.filter(pk=row["pk"]).update(
                            extracted_attributes=attrs, generated_seo_title=fields["generated_seo_title"]
                        )
                    else:
                        names = list(row["fields"])
                        current = model.objects.select_for_update().filter(pk=row["pk"]).values(*names).first()
                        if current is None:
                            continue
                        snapshot.write(json.dumps({"model": row["model"], "pk": row["pk"], "fields": current}, ensure_ascii=False) + "\n")
                        model.objects.filter(pk=row["pk"]).update(**row["fields"])
                        _touch_restored(row["model"], row["pk"])
                    restored += 1
                _sync(snapshot)
    return restored


def _touch_restored(label: str, pk: int) -> None:
    """После возврата SEO lastmod в sitemap тоже меняется (см. ``_touch``)."""
    if label == DOMAIN_LABEL:
        _touch(None, pk)
    elif label == PRODUCT_LABEL:
        _touch(pk, None)
    elif label == "catalog.supplementproducttranslation":
        _touch(None, _model(label).objects.filter(pk=pk).values_list("product_id", flat=True).first())
    elif label == "catalog.producttranslation":
        _touch(_model(label).objects.filter(pk=pk).values_list("product_id", flat=True).first(), None)
