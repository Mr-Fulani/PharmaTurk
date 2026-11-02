"""Пересчёт названия и SEO опубликованных лекарств кодом, без модели (TD-028).

Название (``build_medicine_title`` + МНН) и SEO (``medicine_seo``) лекарства собирает код. У
лекарств, обработанных до нового кода, на сайте старые название и SEO. Пересчёт берёт
входные данные последнего применённого лога и пишет новые значения туда, где ещё лежит
то, что записала обработка (или исходное турецкое название). Поле, изменённое
вручную после обработки, не трогается. Если новое название или SEO хуже текущего (турецкие
слова, пропали форма, дозировка, вещество или русское описание), остаётся текущее.

Где лежат значения: переводы ``MedicineProductTranslation`` (ru и en — своё название и SEO),
базовый ``Product`` и доменный ``MedicineProduct`` (название — RU, SEO — EN, как пишет
``MedicineAIApplier``).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any, Optional

from django.db import transaction
from django.utils import timezone

from apps.ai.services.medicine_reference import fold_tr
from apps.ai.services.medicine_title import title_brand
from apps.ai.services.semantic_validator import _title_has_turkish_words

SEO_FIELDS = ("meta_title", "og_title", "meta_description", "og_description", "meta_keywords")

# Просмотр 01.11.2026 (1 194 товара): шаблон терял форму («RISPERDAL CONSTA 25 мг из Турции»),
# вещество, вторую дозировку («SERETIDE 100/50 мкг» → «100 мкг») и оставлял турецкие слова
# («BRAIN-SPECT RADYOFARMASOTIK HAZIRLAMA KITI»). Такое поле остаётся как есть.
# Шприц, флакон, ампула — упаковка, не форма: «HIBOR …, 2 шприца» без «раствора» — форма пропала.
# Основа формы и путь введения — отдельно: «раствор для инъекций» → «для инъекций» (AMARGINE) теряет
# основу; «раствор для инфузий» → «раствор для инъекций» (BIOFLEKS IZOMIX, «ENJEKTABL SOL» источника
# шаблон переводит дословно) меняет путь — ревью PR #287.
_FORM_WORDS = {
    "ru": re.compile(
        r"таблет|капсул|драже|раствор|суспенз|эмульс|сироп|капл|спрей|аэрозол|мазь|крем|гел[ья]|паст[аы]|"
        r"пен[аы]|порош|гранул|лиофил|концентрат|суппозит|свеч|овул|пессар|пастил|пластыр|шампун|лосьон|"
        r"набор|имплант|жидкост|присыпк"
    ),
    "en": re.compile(
        r"tablet|capsule|drag[eé]e|solution|suspension|emulsion|syrup|drops|spray|aerosol|ointment|cream|"
        r"\bgel\b|paste|foam|powder|granule|lyophili|concentrate|suppositor|ovule|pessar|lozenge|patch|shampoo|"
        r"lotion|\bkit\b|implant|liquid"
    ),
}
_ROUTE_WORDS = {"ru": re.compile(r"инъекц|инфуз|ингал"), "en": re.compile(r"inject|infusion|inhal")}
# Изотоп в скобках — часть вещества радиофармпрепарата: «(18F)», «(99mTc)».
_ISOTOPE_RE = re.compile(
    r"\((\d{1,3}m?(?:tc|ga|in|tl|lu|ra|sm|xe|cr|f|i|y)|(?:tc|ga|in|tl|lu|ra|sm|xe|cr|f|i|y)-?\d{1,3}m?)\)"
)
# Дозировка — число с единицей: «37,5 мг», «100 мкг/50 мкг», «1.000.000 МЕ», «10 000 МЕ», «0,1%».
_DOSE_RE = re.compile(
    r"(\d{1,3}(?:[ \u00a0]\d{3})+|\d+(?:[.,]\d+)*)\s*(%|мкг|мг|мл|ме|ед|mcg|mg|ml|iu)(?![a-zа-яё])", re.IGNORECASE
)
_DOSE_UNITS = {"мкг": "mcg", "мг": "mg", "мл": "ml", "ме": "iu", "ед": "iu"}
# Слова вещества, по которым его не узнать: соли, «экстракт», «витамин».
_INGREDIENT_COMMON = frozenset({
    "hidroklorur", "hydrochloride", "sodyum", "sodium", "potasyum", "potassium", "kalsiyum", "calcium",
    "magnezyum", "magnesium", "sulfat", "sulfate", "sulphate", "asetat", "acetate", "fosfat", "phosphate",
    "klorur", "chloride", "bromur", "bromide", "maleat", "maleate", "tartrat", "tartrate", "mesilat",
    "besilat", "monohidrat", "dihidrat", "trihidrat", "ekstresi", "extract", "vitamin", "insan", "human",
    "normal", "хлорид", "натрия", "калия", "кальция", "гидрохлорид", "экстракт", "витамин",
})
# Русские слова, которые описанием не считаются: «60 доз», «30 шт.», «100 мкг».
_NOT_DESCRIPTION = frozenset({"доз", "мкг", "мкл"})


@dataclass
class Change:
    obj: Any
    field: str
    old: str
    new: str
    locale: str = ""

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


def _doses(text: str) -> set[tuple[str, str]]:
    """{("37.5", "mg"), ("1000000", "iu")}: «37,5 мг» и «37.5 mg», «1.000.000 МЕ» и «1000000 IU» — одно и то же."""
    return {
        (re.sub(r"[., \u00a0](?=\d{3}(?:\D|$))", "", number).replace(",", "."), _DOSE_UNITS.get(unit.lower(), unit.lower()))
        for number, unit in _DOSE_RE.findall(text)
    }


def _ingredient_stems(*values: Any) -> set[str]:
    """Начала слов вещества («рисперидон», «Risperidon» → «риспер», «risper»): так находятся и формы слова."""
    words = (word for value in values for word in re.findall(r"[a-zа-яё]{5,}", fold_tr(value)))
    return {word[:6] for word in words if word not in _INGREDIENT_COMMON}


def _latin_words(text: str) -> set[str]:
    return {word.lower() for word in re.findall(r"[A-Za-zÇçĞğİıÖöŞşÜü]{3,}", text) if not re.fullmatch(r"[IVXL]+", word)}


def _description_words(text: str) -> list[str]:
    return [word for word in re.findall(r"[а-яё]{3,}", text.lower()) if word not in _NOT_DESCRIPTION]


def worse_reasons(field: str, locale: str, old: str, new: str, ingredient: set[str], brand: str = "") -> list[str]:
    """Чем новое значение поля хуже текущего; [] — не хуже.

    ``ingredient`` — начала слов вещества (``_ingredient_stems``); бренд из поиска вещества
    убирается: «RISPERDAL» начинается как «рисперидон», но веществом не считается.
    """
    if field == "meta_keywords" or not old:
        return []
    reasons = []
    forms = _FORM_WORDS[locale]
    if forms.search(old.lower()) and not forms.search(new.lower()):
        reasons.append("форма")
    routes = _ROUTE_WORDS[locale]
    if set(routes.findall(old.lower())) - set(routes.findall(new.lower())):
        reasons.append("путь введения")
    brand_words = set(fold_tr(brand).split())

    def without_brand(text: str) -> str:
        return " ".join(word for word in fold_tr(text).split() if word.strip(",.()") not in brand_words)

    old_text, new_text = without_brand(old), without_brand(new)
    # «fludeoxyglucose (18F)»: МНН нет в памяти, а турецкое «Florodeoksiglukoz» в английском не узнать.
    lost_isotope = set(_ISOTOPE_RE.findall(old_text)) - set(_ISOTOPE_RE.findall(new_text))
    if lost_isotope or (
        any(stem in old_text for stem in ingredient) and not any(stem in new_text for stem in ingredient)
    ):
        reasons.append("вещество")
    if field != "name":
        return reasons  # фасовку и вторую дозировку SEO-шаблон убирает сам, по плану
    if _doses(old) - _doses(new):
        reasons.append("дозировка")
    if locale == "ru":
        # «RADYOFARMASOTIK HAZIRLAMA KITI» вместо «радиофармацевтический набор»; римское «VIII» — не слово.
        latin = _latin_words(new) - _latin_words(old)
        if latin or _title_has_turkish_words(new):
            reasons.append("латиница вместо перевода")
        if _description_words(old) and not _description_words(new):
            reasons.append("нет русского описания")
    return reasons


def latest_applied_log(product_id: int):
    from apps.ai.models import AIProcessingLog

    return (
        AIProcessingLog.objects.filter(
            product_id=product_id, processing_type="full", application_status__in=("applied", "partial")
        )
        .order_by("-id")
        .first()
    )


def plan_refresh(product, log, generator) -> tuple[list[Change], Optional[dict], list[str]]:
    """Изменения товара: (список, новые значения {"ru": …, "en": …}, что оставлено) или ([], None, []).

    Если новое название хуже текущего хотя бы в одном поле, все поля названия товара
    остаются текущими, так же и SEO; «что оставлено» — ["название: форма", "SEO: вещество"].
    """
    input_data = log.input_data or {}
    code = generator._build_medicine_code_fields(input_data, allow_llm=False)
    if not code.get("title") or not code.get("seo"):
        return [], None, []
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
                changes.append(Change(obj, field, current, value, locale))
    # Вещество из полей товара тоже: МНН нет в памяти — у кода остаётся только турецкое написание.
    ingredient = _ingredient_stems(
        input_data.get("active_ingredient"), code["ru"].get("active_ingredient"), code["en"].get("active_ingredient"),
        *(getattr(obj, "active_ingredient", "") for obj, _name_locale, _seo_locale in targets),
    )
    brand = title_brand(source)
    kept = {}
    for change in changes:
        for reason in worse_reasons(change.field, change.locale, change.old, change.new, ingredient, brand):
            kept[f"{_group(change.field)}: {reason}"] = None
    groups = {reason.split(":")[0] for reason in kept}
    return [change for change in changes if _group(change.field) not in groups], new, list(kept)


def _group(field: str) -> str:
    return "название" if field == "name" else "SEO"


def apply_refresh(log, changes: list[Change], new: dict) -> None:
    """Записать изменения и обновить лог: следующий пересчёт сравнивает с новыми значениями.

    Название или SEO, оставленные текущими (``plan_refresh``), в логе не обновляются:
    следующий пересчёт снова сравнит их с тем, что записала обработка.
    """
    names = any(change.field == "name" for change in changes)
    seo_written = any(change.field != "name" for change in changes)
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
            if seo_written:
                entry.update({field: new[locale][field] for field in SEO_FIELDS})
            if names:
                entry["generated_title"] = new[locale]["name"]
            seo[locale] = entry
        attrs["seo_translations"] = seo
        attrs["code_fields_refreshed_at"] = timezone.now().isoformat()
        log.extracted_attributes = attrs
        if names:
            log.generated_title = new["ru"]["name"]
        if seo_written:
            log.generated_seo_title = new["ru"]["meta_title"][:70]
        log.save(update_fields=["extracted_attributes", "generated_title", "generated_seo_title"])
