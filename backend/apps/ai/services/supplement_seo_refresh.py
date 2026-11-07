"""Пересборка SEO БАДов кодом из готовых AI-логов, без модели (SEO-ядро 07.11.2026, ревью #333).

SEO БАДа (title, description, keywords) собирает ``supplement_content.build_seo`` из частей названия:
бренд, бренд кириллицей, «что это», фасовка. Эти части лежат в логе обработки
(``raw_llm_response.rule_content.supplement``), поэтому новый шаблон можно применить ко всем БАДам
без запросов к модели. Название (H1, ``name``) не меняется.

- Входные данные — лог, по которому собрано название на сайте: круг описаний БАДов возвращает
  прежние название и SEO, и последний лог может описывать другое название.
- Перезаписывается только то, что записала какая-либо обработка товара (или пусто): поле,
  изменённое вручную, остаётся.
- «Инструкция на русском» — по текущему описанию на сайте: если модератор убрал абзац «Способ
  применения», SEO его не обещает.

Где лежит SEO БАДа: ``SupplementProduct`` (SEO — EN, как пишет применение лога; ``Product``
получает его синхронизацией при сохранении), переводы ``SupplementProductTranslation`` и
``ProductTranslation`` (ru и en — своё SEO).
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any, Optional

from django.db import transaction
from django.utils import timezone

from apps.ai.services import supplement_content
from apps.ai.services.medicine_refresh import Change, _keywords_text

SEO_FIELDS = ("meta_title", "og_title", "meta_description", "og_description", "meta_keywords")
_LINE_NUMBER_RE = re.compile(r"\d[\d/.,]*\+?")


def _supplement_data(log) -> dict:
    rule = (log.raw_llm_response or {}).get("rule_content") if isinstance(log.raw_llm_response, dict) else None
    data = (rule or {}).get("supplement") if isinstance(rule, dict) else None
    return data if isinstance(data, dict) else {}


def _logged_name(log, locale: str) -> str:
    seo = ((log.extracted_attributes or {}).get("seo_translations") or {}).get(locale) or {}
    return str(seo.get("generated_title") or (log.generated_title if locale == "ru" else "") or "").strip()


def _logged_seo(log, locale: str) -> dict[str, str]:
    seo = ((log.extracted_attributes or {}).get("seo_translations") or {}).get(locale) or {}
    values = {field: str(seo.get(field) or "").strip() for field in SEO_FIELDS}
    values["meta_keywords"] = _keywords_text(seo.get("meta_keywords"))
    return values


def supplement_logs(product_id: int) -> list:
    from apps.ai.models import AIProcessingLog

    return list(
        AIProcessingLog.objects.filter(product_id=product_id)
        .only("id", "raw_llm_response", "extracted_attributes", "generated_title", "generated_seo_title")
        .order_by("-id")
    )


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


def _targets(product) -> list[tuple[Any, str]]:
    """(объект, локаль SEO)."""
    from apps.catalog.models import ProductTranslation

    domain = getattr(product, "domain_item", None)
    if domain is None or domain is product:
        return []
    targets = [(domain, "en")]
    targets += [(t, t.locale) for t in domain.translations.filter(locale__in=("ru", "en"))]
    targets += [(t, t.locale) for t in ProductTranslation.objects.filter(product=product, locale__in=("ru", "en"))]
    return targets


def _current_ru(product) -> tuple[str, str]:
    """Название и описание RU на сайте: перевод домена → домен → товар."""
    domain = getattr(product, "domain_item", None)
    translation = domain.translations.filter(locale="ru").first() if domain is not None else None
    name = (getattr(translation, "name", "") or getattr(domain, "name", "") or product.name or "").strip()
    description = (
        getattr(translation, "description", "") or getattr(domain, "description", "") or product.description or ""
    )
    return name, description


def plan_seo(product, logs: Optional[list] = None) -> tuple[list[Change], Optional[dict], str]:
    """(изменения, новые значения {"ru": …, "en": …}, причина пропуска или "")."""
    logs = supplement_logs(product.id) if logs is None else logs
    name, description = _current_ru(product)
    source_log = next((log for log in logs if _supplement_data(log) and _logged_name(log, "ru") == name), None)
    if source_log is None:
        reason = "нет лога кода БАДа" if not any(_supplement_data(log) for log in logs) else "название не из лога"
        return [], None, reason
    data = _supplement_data(source_log)
    product_text = data.get("product") if isinstance(data.get("product"), dict) else {}
    if not product_text.get("ru"):
        return [], None, "в логе нет «что это»"
    pack_data = data.get("pack") if isinstance(data.get("pack"), dict) else None
    pack = SimpleNamespace(ru=pack_data.get("ru", ""), en=pack_data.get("en", "")) if pack_data else None
    seo = supplement_content.build_seo(
        title_brand(str(data.get("brand") or ""), name, product_text["ru"]),
        str(data.get("brand_ru") or ""),
        product_text,
        pack,
        baby_food=bool(data.get("baby_food")),
        usage=supplement_content.has_usage_paragraph(description),
    )
    new = {
        locale: {
            "meta_title": seo[locale]["seo_title"],
            "og_title": seo[locale]["seo_title"],
            "meta_description": seo[locale]["seo_description"],
            "og_description": seo[locale]["seo_description"],
            "meta_keywords": _keywords_text(seo[locale]["keywords"]),
        }
        for locale in ("ru", "en")
    }
    # Что записывала любая обработка товара: после круга описаний на сайте SEO прошлого лога.
    logged = {locale: [_logged_seo(log, locale) for log in logs] for locale in ("ru", "en")}
    changes = []
    for obj, locale in _targets(product):
        for field in SEO_FIELDS:
            current = str(getattr(obj, field, "") or "").strip()
            value = new[locale][field]
            if current == value:
                continue
            if current == "" or any(current == values[field] for values in logged[locale]):
                changes.append(Change(obj, field, current, value, locale))
    return changes, {"log": source_log, **new}, ""


def apply_seo(changes: list[Change], new: dict) -> None:
    """Записать и отметить в логе: следующая пересборка сверяет поля уже с новыми значениями."""
    if not changes:
        return
    log = new["log"]
    with transaction.atomic():
        by_obj: dict[int, tuple[Any, set]] = {}
        for change in changes:
            setattr(change.obj, change.field, change.new)
            by_obj.setdefault(id(change.obj), (change.obj, set()))[1].add(change.field)
        # Переводы — до домена: сохранение домена синхронизирует Product.
        for obj, fields in sorted(by_obj.values(), key=lambda item: hasattr(item[0], "translations")):
            obj.save(update_fields=sorted(fields))
        attrs = dict(log.extracted_attributes or {})
        seo = dict(attrs.get("seo_translations") or {})
        for locale in ("ru", "en"):
            seo[locale] = {**dict(seo.get(locale) or {}), **new[locale]}
        attrs["seo_translations"] = seo
        attrs["supplement_seo_rebuilt_at"] = timezone.now().isoformat()
        log.extracted_attributes = attrs
        log.generated_seo_title = new["ru"]["meta_title"][:70]
        log.save(update_fields=["extracted_attributes", "generated_seo_title"])
