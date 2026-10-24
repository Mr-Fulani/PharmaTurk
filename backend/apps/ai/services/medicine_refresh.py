"""Пересчёт названия и SEO опубликованных лекарств кодом, без модели (TD-028).

Название (``build_medicine_title`` + МНН) и SEO (``medicine_seo``) лекарства собирает код. У
лекарств, обработанных до нового кода, на сайте старые название и SEO. Пересчёт берёт
входные данные последнего применённого лога и пишет новые значения туда, где ещё лежит
то, что записала обработка (или исходное турецкое название). Поле, изменённое
вручную после обработки, не трогается.

Где лежат значения: переводы ``MedicineProductTranslation`` (ru и en — своё название и SEO),
базовый ``Product`` и доменный ``MedicineProduct`` (название — RU, SEO — EN, как пишет
``MedicineAIApplier``).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, Optional

from django.db import transaction
from django.utils import timezone

SEO_FIELDS = ("meta_title", "og_title", "meta_description", "og_description", "meta_keywords")


@dataclass
class Change:
    obj: Any
    field: str
    old: str
    new: str

    @property
    def label(self) -> str:
        locale = getattr(self.obj, "locale", "")
        return f"{type(self.obj).__name__}{'[' + locale + ']' if locale else ''}.{self.field}"


def _keywords_text(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    text = str(value or "").strip()
    if text.startswith("["):  # в логе список сохранялся строкой «['ARPIN', 'Арпин']»
        try:
            return _keywords_text(ast.literal_eval(text))
        except (ValueError, SyntaxError):
            return text
    return text


def _code_values(title: dict, seo: dict, locale: str) -> dict[str, str]:
    values = seo[locale]
    return {
        "name": title[locale],
        "meta_title": values["seo_title"],
        "og_title": values["seo_title"],
        "meta_description": values["seo_description"],
        "og_description": values["seo_description"],
        "meta_keywords": _keywords_text(values["keywords"]),
    }


def _logged_values(log, locale: str) -> dict[str, str]:
    """Что записала обработка: SEO и название этого лога (``seo_translations``)."""
    seo = ((log.extracted_attributes or {}).get("seo_translations") or {}).get(locale) or {}
    values = {field: str(seo.get(field) or "").strip() for field in SEO_FIELDS}
    values["meta_keywords"] = _keywords_text(seo.get("meta_keywords"))
    values["name"] = str(seo.get("generated_title") or (log.generated_title if locale == "ru" else "") or "").strip()
    return values


def latest_applied_log(product_id: int):
    from apps.ai.models import AIProcessingLog

    return (
        AIProcessingLog.objects.filter(
            product_id=product_id, processing_type="full", application_status__in=("applied", "partial")
        )
        .order_by("-id")
        .first()
    )


def plan_refresh(product, log, generator) -> tuple[list[Change], Optional[dict]]:
    """Изменения для товара: (список, новые значения {"ru": …, "en": …}) или ([], None)."""
    input_data = log.input_data or {}
    code = generator._build_medicine_code_fields(input_data, allow_llm=False)
    if not code.get("title") or not code.get("seo"):
        return [], None
    new = {locale: _code_values(code["title"], code["seo"], locale) for locale in ("ru", "en")}
    logged = {locale: _logged_values(log, locale) for locale in ("ru", "en")}
    source = str(input_data.get("name") or "").strip()
    domain = getattr(product, "medicine_item", None)
    targets = [(product, "ru", "en"), (domain, "ru", "en")] if domain else [(product, "ru", "en")]
    if domain:
        targets += [(t, t.locale, t.locale) for t in domain.translations.filter(locale__in=("ru", "en"))]
    changes = []
    for obj, name_locale, seo_locale in targets:
        for field in ("name",) + SEO_FIELDS:
            if not hasattr(obj, field):
                continue
            locale = name_locale if field == "name" else seo_locale
            current = str(getattr(obj, field) or "").strip()
            value = new[locale][field]
            if current == value:
                continue
            # Перезаписываем только то, что не правили руками: значение обработки, пусто или исходник.
            if current in ("", logged[locale][field]) or (field == "name" and current == source):
                changes.append(Change(obj, field, current, value))
    return changes, new


def apply_refresh(log, changes: list[Change], new: dict) -> None:
    """Записать изменения и обновить лог: следующий пересчёт сравнивает с новыми значениями."""
    with transaction.atomic():
        by_obj: dict[int, tuple[Any, set]] = {}
        for change in changes:
            setattr(change.obj, change.field, change.new)
            by_obj.setdefault(id(change.obj), (change.obj, set()))[1].add(change.field)
        for obj, fields in by_obj.values():
            obj.save(update_fields=sorted(fields))
        attrs = dict(log.extracted_attributes or {})
        seo = dict(attrs.get("seo_translations") or {})
        for locale in ("ru", "en"):
            entry = dict(seo.get(locale) or {})
            entry.update({field: new[locale][field] for field in SEO_FIELDS})
            entry["generated_title"] = new[locale]["name"]
            seo[locale] = entry
        attrs["seo_translations"] = seo
        attrs["code_fields_refreshed_at"] = timezone.now().isoformat()
        log.extracted_attributes = attrs
        log.generated_title = new["ru"]["name"]
        log.generated_seo_title = new["ru"]["meta_title"][:70]
        log.save(update_fields=["extracted_attributes", "generated_title", "generated_seo_title"])
