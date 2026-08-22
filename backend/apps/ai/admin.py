import json
from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseNotAllowed, HttpResponseRedirect
from django.utils.html import format_html, escape
from django.utils.safestring import mark_safe
from django.urls import path, reverse, NoReverseMatch
from apps.catalog.product_semantics import looks_untranslated_turkish

from .models import (
    AIApplicationStatus,
    AIProcessingLog,
    AIProcessingStatus,
    AIModerationQueue,
    AITemplate,
)
from .services.moderation import (
    APPLICATION_LABELS,
    MEDICINE_TRANSLATION_FIELD_LABELS,
    build_change_preview,
    get_incomplete_medicine_field_messages,
    get_moderation_reason_labels,
    get_rejected_field_labels,
    get_workflow_title,
    reject_log,
)
from .services.size_inventory import (
    merge_confirmed_sizes,
    parse_moderator_size_list,
    strip_size_inventory_sentences,
    supports_size_inventory,
)


# Атрибуты украшений для формы модерации (применяются к JewelryProduct)
JEWELRY_TYPE_CHOICES = [
    ("", "—"),
    ("ring", "Кольцо"),
    ("bracelet", "Браслет"),
    ("necklace", "Цепь/ожерелье"),
    ("earrings", "Серьги"),
    ("pendant", "Подвеска"),
]
GENDER_CHOICES_FORM = [
    ("", "—"),
    ("men", "Мужская"),
    ("women", "Женская"),
    ("unisex", "Унисекс"),
    ("kids", "Детская"),
]
JEWELRY_FORM_FIELDS = (
    "jewelry_type",
    "material",
    "metal_purity",
    "stone_type",
    "carat_weight",
    "gender",
)

MEDICINE_EDITOR_FIELDS = tuple(MEDICINE_TRANSLATION_FIELD_LABELS)
MEDICINE_CLINICAL_FIELDS = frozenset(
    {
        "indications",
        "usage_instructions",
        "side_effects",
        "contraindications",
        "storage_conditions",
    }
)
MEDICINE_LONG_TEXT_FIELDS = MEDICINE_CLINICAL_FIELDS | {"special_notes"}
MEDICINE_EDITOR_DECISIONS = (
    ("apply", "Применить RU и EN из формы"),
    (
        "merge_current",
        "Применить новое; отсутствующий язык сохранить из товара",
    ),
    ("keep_current", "Не менять этот раздел товара"),
)


def _medicine_editor_field_name(field_name, suffix):
    return f"medicine_{field_name}_{suffix}"


def _medicine_editor_label(field_name):
    return MEDICINE_TRANSLATION_FIELD_LABELS[field_name].removesuffix(" RU/EN").capitalize()


def _usable_current_medicine_translation(value, *, locale, source_length=0):
    """Accept an existing locale only as a visible fallback for a missing AI value."""
    text = str(value or "").strip()
    if len(text) < 10:
        return False
    if locale == "ru" and looks_untranslated_turkish(text):
        return False
    if source_length >= 300 and len(text) / source_length < 0.45:
        return False
    return True


def _medicine_current_translation_fallbacks(log):
    """Return usable current RU/EN values missing from an incomplete AI result."""
    product = getattr(log, "product", None)
    if getattr(product, "product_type", None) != "medicines":
        return {}
    attrs = log.extracted_attributes if isinstance(log.extracted_attributes, dict) else {}
    translations_data = (
        attrs.get("translations_data")
        if isinstance(attrs.get("translations_data"), dict)
        else {}
    )
    quality = (
        attrs.get("medicine_translation_quality")
        if isinstance(attrs.get("medicine_translation_quality"), dict)
        else {}
    )
    target = getattr(product, "domain_item", None)
    translation_manager = getattr(target, "translations", None)
    if translation_manager is None:
        return {}
    current_translations = {
        locale: translation_manager.filter(locale=locale).first()
        for locale in ("ru", "en")
    }
    fallbacks = {}
    for medicine_field in MEDICINE_CLINICAL_FIELDS:
        details = quality.get(medicine_field)
        if not isinstance(details, dict) or details.get("complete", False):
            continue
        source_length = int(details.get("source_length") or 0)
        field_fallbacks = {}
        for locale in ("ru", "en"):
            proposed = str(
                (translations_data.get(locale) or {}).get(medicine_field) or ""
            ).strip()
            if proposed:
                continue
            current_translation = current_translations.get(locale)
            current_value = (
                getattr(current_translation, medicine_field, "")
                if current_translation is not None
                else ""
            )
            if _usable_current_medicine_translation(
                current_value,
                locale=locale,
                source_length=source_length,
            ):
                field_fallbacks[locale] = str(current_value).strip()
        if field_fallbacks:
            fallbacks[medicine_field] = field_fallbacks
    return fallbacks


def _persist_medicine_current_translation_fallbacks(log):
    """Persist safe current-locale fallbacks for the one-click medicine action."""
    fallbacks = _medicine_current_translation_fallbacks(log)
    if not fallbacks:
        return {}
    attrs = dict(log.extracted_attributes or {})
    translations_data = dict(attrs.get("translations_data") or {})
    translations = {
        locale: dict(translations_data.get(locale) or {})
        for locale in ("ru", "en")
    }
    quality = dict(attrs.get("medicine_translation_quality") or {})
    decisions = dict(attrs.get("medicine_moderator_decisions") or {})
    overrides = dict(attrs.get("medicine_moderator_overrides") or {})
    preserved_locales = dict(attrs.get("medicine_moderator_preserved_locales") or {})
    used_fallbacks = {}
    for medicine_field, field_fallbacks in fallbacks.items():
        if decisions.get(medicine_field, "apply") not in {"apply", "merge_current"}:
            continue
        for locale, value in field_fallbacks.items():
            translations[locale][medicine_field] = value
        decisions[medicine_field] = "merge_current"
        used_locales = [
            locale for locale in ("ru", "en") if locale in field_fallbacks
        ]
        preserved_locales[medicine_field] = used_locales
        ru_value = str(translations["ru"].get(medicine_field) or "").strip()
        en_value = str(translations["en"].get(medicine_field) or "").strip()
        overrides[medicine_field] = {
            "ru": ru_value,
            "en": en_value,
            "decision": "merge_current",
        }
        details = dict(quality.get(medicine_field) or {})
        ru_complete = bool(ru_value) and not looks_untranslated_turkish(ru_value)
        en_complete = bool(en_value)
        details.update(
            {
                "ru_length": len(ru_value),
                "en_length": len(en_value),
                "ru_complete": ru_complete,
                "en_complete": en_complete,
                "complete": ru_complete and en_complete,
                "moderator_reviewed": True,
            }
        )
        quality[medicine_field] = details
        used_fallbacks[medicine_field] = used_locales
    if not used_fallbacks:
        return {}
    translations_data.update(translations)
    attrs["translations_data"] = translations_data
    attrs["medicine_translation_quality"] = quality
    attrs["medicine_moderator_decisions"] = decisions
    attrs["medicine_moderator_overrides"] = overrides
    attrs["medicine_moderator_preserved_locales"] = preserved_locales
    log.extracted_attributes = attrs
    log.save(update_fields=["extracted_attributes", "updated_at"])
    return used_fallbacks


MEDICINE_EDITOR_FORM_FIELDS = tuple(
    _medicine_editor_field_name(field_name, suffix)
    for field_name in MEDICINE_EDITOR_FIELDS
    for suffix in ("ru", "en", "decision")
)
MEDICINE_CLINICAL_EDITOR_ROWS = tuple(
    tuple(
        _medicine_editor_field_name(field_name, suffix)
        for suffix in ("ru", "en", "decision")
    )
    for field_name in MEDICINE_EDITOR_FIELDS
    if field_name in MEDICINE_CLINICAL_FIELDS
)
MEDICINE_DETAIL_EDITOR_ROWS = tuple(
    tuple(
        _medicine_editor_field_name(field_name, suffix)
        for suffix in ("ru", "en", "decision")
    )
    for field_name in MEDICINE_EDITOR_FIELDS
    if field_name not in MEDICINE_CLINICAL_FIELDS
)


class AIProcessingLogForm(forms.ModelForm):
    """Форма с полями EN/OG и атрибутами украшений; всё хранится в extracted_attributes и применяется к товару."""
    generated_en_title = forms.CharField(
        max_length=255,
        required=False,
        label="Заголовок (EN)",
        help_text="Английское название — уходит в перевод en и в карточку товара.",
        widget=forms.TextInput(attrs={"size": 80}),
    )
    generated_en_description = forms.CharField(
        required=False,
        label="Описание (EN)",
        help_text="Английское описание — уходит в перевод en.",
        widget=forms.Textarea(attrs={"rows": 4, "cols": 80}),
    )
    og_title = forms.CharField(
        max_length=255,
        required=False,
        label="OG title",
        help_text="og:title для соцсетей (латиница).",
        widget=forms.TextInput(attrs={"size": 80}),
    )
    og_description = forms.CharField(
        max_length=255,
        required=False,
        label="OG description",
        help_text="og:description для соцсетей (латиница).",
        widget=forms.Textarea(attrs={"rows": 2, "cols": 80}),
    )
    inventory_sizes = forms.CharField(
        required=False,
        label="Доступные размеры",
        help_text=(
            "Через запятую. При применении размеры добавятся в карточку товара; "
            "существующие размеры и остатки не удаляются."
        ),
        widget=forms.TextInput(attrs={"size": 80, "placeholder": "M, XL, 2XL"}),
    )
    # Атрибуты украшений (применяются к JewelryProduct при «Сохранить и применить»)
    jewelry_type = forms.ChoiceField(
        choices=JEWELRY_TYPE_CHOICES,
        required=False,
        label="Тип украшения",
        widget=forms.Select(attrs={"style": "max-width: 200px"}),
    )
    material = forms.CharField(
        max_length=100,
        required=False,
        label="Материал",
        widget=forms.TextInput(attrs={"size": 40}),
    )
    metal_purity = forms.CharField(
        max_length=50,
        required=False,
        label="Проба металла",
        help_text="Напр. 925, 585",
        widget=forms.TextInput(attrs={"size": 20}),
    )
    stone_type = forms.CharField(
        max_length=100,
        required=False,
        label="Тип камня",
        widget=forms.TextInput(attrs={"size": 40}),
    )
    carat_weight = forms.DecimalField(
        required=False,
        label="Вес камней (карат)",
        min_value=0,
        max_digits=6,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "style": "width: 100px"}),
    )
    gender = forms.ChoiceField(
        choices=GENDER_CHOICES_FORM,
        required=False,
        label="Пол",
        widget=forms.Select(attrs={"style": "max-width: 120px"}),
    )

    # Поля объявляются на уровне класса, чтобы Django Admin мог безопасно
    # включать их в fieldsets. В форме они остаются только для medicines.
    for _medicine_field in MEDICINE_EDITOR_FIELDS:
        _medicine_label = _medicine_editor_label(_medicine_field)
        _medicine_widget = (
            forms.Textarea(attrs={"rows": 6, "cols": 72})
            if _medicine_field in MEDICINE_LONG_TEXT_FIELDS
            else forms.TextInput(attrs={"size": 72})
        )
        locals()[_medicine_editor_field_name(_medicine_field, "ru")] = forms.CharField(
            required=False,
            label=f"{_medicine_label} (RU)",
            widget=_medicine_widget,
        )
        _medicine_widget_en = (
            forms.Textarea(attrs={"rows": 6, "cols": 72})
            if _medicine_field in MEDICINE_LONG_TEXT_FIELDS
            else forms.TextInput(attrs={"size": 72})
        )
        locals()[_medicine_editor_field_name(_medicine_field, "en")] = forms.CharField(
            required=False,
            label=f"{_medicine_label} (EN)",
            widget=_medicine_widget_en,
        )
        locals()[_medicine_editor_field_name(_medicine_field, "decision")] = forms.ChoiceField(
            required=False,
            label=f"Действие: {_medicine_label}",
            choices=MEDICINE_EDITOR_DECISIONS,
            initial="apply",
            widget=forms.Select(attrs={"style": "min-width: 270px"}),
        )
    del _medicine_field, _medicine_label, _medicine_widget, _medicine_widget_en

    class Meta:
        model = AIProcessingLog
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["generated_title"].label = "Название (RU)"
        self.fields["generated_description"].label = "Описание (RU)"
        self.fields["generated_seo_title"].label = "SEO title (RU)"
        self.fields["generated_seo_description"].label = "SEO description (RU)"
        self.fields["generated_keywords"].label = "Ключевые слова (RU)"
        product = getattr(self.instance, "product", None) if self.instance else None
        product_type = getattr(product, "product_type", None)
        attrs = self.instance.extracted_attributes or {} if self.instance else {}
        self._medicine_initial_values = {}
        self._medicine_fallback_values = {}
        if self.instance and self.instance.pk:
            seo_translations = attrs.get("seo_translations") or {}
            seo_en = seo_translations.get("en") or attrs.get("seo_en") or {}
            self.fields["generated_en_title"].initial = seo_en.get("generated_title") or ""
            self.fields["generated_en_description"].initial = seo_en.get("generated_description") or ""
            self.fields["og_title"].initial = seo_en.get("og_title") or ""
            self.fields["og_description"].initial = seo_en.get("og_description") or ""
            # Атрибуты украшений из лога или с карточки товара
            self.fields["jewelry_type"].initial = attrs.get("jewelry_type") or ""
            self.fields["material"].initial = attrs.get("material") or ""
            self.fields["metal_purity"].initial = attrs.get("metal_purity") or ""
            self.fields["stone_type"].initial = attrs.get("stone_type") or ""
            self.fields["carat_weight"].initial = attrs.get("carat_weight")
            self.fields["gender"].initial = attrs.get("gender") or ""
            if product and getattr(product, "product_type", None) == "jewelry":
                domain = getattr(product, "jewelry_item", None)
                if domain and not attrs.get("metal_purity") and getattr(domain, "metal_purity", None):
                    self.fields["metal_purity"].initial = domain.metal_purity
                if domain and not attrs.get("material") and getattr(domain, "material", None):
                    self.fields["material"].initial = domain.material
                if domain and not attrs.get("jewelry_type") and getattr(domain, "jewelry_type", None):
                    self.fields["jewelry_type"].initial = domain.jewelry_type
                if domain and not attrs.get("stone_type") and getattr(domain, "stone_type", None):
                    self.fields["stone_type"].initial = domain.stone_type
                if domain and getattr(domain, "gender", None):
                    self.fields["gender"].initial = domain.gender or ""
            else:
                # Эти поля имеют смысл только для JewelryAIApplier. Если оставить
                # их в bound-форме другого типа, пустые значения могут затереть
                # одноимённые ключи extracted_attributes чужой категории.
                for field_name in JEWELRY_FORM_FIELDS:
                    self.fields.pop(field_name, None)
        elif product_type != "jewelry":
            for field_name in JEWELRY_FORM_FIELDS:
                self.fields.pop(field_name, None)

        if supports_size_inventory(product_type):
            effective_attrs = merge_confirmed_sizes(
                attrs,
                getattr(self.instance, "input_data", None) or {},
                product_type,
                allow_moderator_override=True,
            )
            self.fields["inventory_sizes"].initial = ", ".join(
                row["size"] for row in effective_attrs.get("sizes") or []
            )
            # Legacy logs may still contain size inventory in generated prose.
            # Show the moderator exactly the cleaned values that the applier
            # will write, instead of making the preview and edit form disagree.
            self.initial["generated_description"] = strip_size_inventory_sentences(
                getattr(self.instance, "generated_description", "")
            )
            self.initial["generated_seo_description"] = strip_size_inventory_sentences(
                getattr(self.instance, "generated_seo_description", "")
            )
            self.fields["generated_en_description"].initial = strip_size_inventory_sentences(
                self.fields["generated_en_description"].initial
            )
            self.fields["og_description"].initial = strip_size_inventory_sentences(
                self.fields["og_description"].initial
            )
        else:
            self.fields.pop("inventory_sizes", None)

        if product_type == "medicines":
            translations_data = (
                attrs.get("translations_data")
                if isinstance(attrs.get("translations_data"), dict)
                else {}
            )
            quality = (
                attrs.get("medicine_translation_quality")
                if isinstance(attrs.get("medicine_translation_quality"), dict)
                else {}
            )
            decisions = (
                attrs.get("medicine_moderator_decisions")
                if isinstance(attrs.get("medicine_moderator_decisions"), dict)
                else {}
            )
            medicine_fallbacks = _medicine_current_translation_fallbacks(
                self.instance
            )
            for medicine_field in MEDICINE_EDITOR_FIELDS:
                ru_field = _medicine_editor_field_name(medicine_field, "ru")
                en_field = _medicine_editor_field_name(medicine_field, "en")
                decision_field = _medicine_editor_field_name(medicine_field, "decision")
                ru_value = str((translations_data.get("ru") or {}).get(medicine_field) or "")
                en_value = str((translations_data.get("en") or {}).get(medicine_field) or "")
                stored_decision = decisions.get(medicine_field) or "apply"
                details = quality.get(medicine_field)
                display_values = {"ru": ru_value, "en": en_value}
                fallback_values = dict(
                    medicine_fallbacks.get(medicine_field) or {}
                )
                for locale, value in fallback_values.items():
                    if not display_values[locale]:
                        display_values[locale] = value
                decision = stored_decision
                if fallback_values and stored_decision in {"apply", "merge_current"}:
                    decision = "merge_current"
                self.fields[ru_field].initial = display_values["ru"]
                self.fields[en_field].initial = display_values["en"]
                self.fields[decision_field].initial = decision
                self._medicine_initial_values[medicine_field] = {
                    "ru": ru_value,
                    "en": en_value,
                    "decision": stored_decision,
                }
                self._medicine_fallback_values[medicine_field] = fallback_values
                if isinstance(details, dict) and not details.get("complete", False):
                    warning = (
                        "Сейчас заблокировано: AI-результат неполный; источник "
                        f"{details.get('source_length', 0)} симв., "
                        f"RU {details.get('ru_length', 0)}, EN {details.get('en_length', 0)}. "
                        "Заполните недостающий язык либо сохраните его текущее значение товара."
                    )
                    self.fields[ru_field].help_text = warning
                    self.fields[en_field].help_text = warning
                if fallback_values:
                    fallback_labels = []
                    for locale, value in fallback_values.items():
                        locale_label = locale.upper()
                        note = (
                            f"AI не создал {locale_label}. В поле подставлен текущий "
                            f"{locale_label} товара ({len(value)} симв.); он не будет потерян."
                        )
                        field_name = ru_field if locale == "ru" else en_field
                        existing_help = str(self.fields[field_name].help_text or "")
                        self.fields[field_name].help_text = f"{note} {existing_help}".strip()
                        fallback_labels.append(locale_label)
                    self.fields[decision_field].help_text = (
                        "Рекомендуемое действие: применить новые данные и сохранить текущий "
                        + "/".join(fallback_labels)
                        + " товара. После применения очередь модерации закроется, если других "
                        "причин блокировки нет."
                    )
        else:
            for field_name in MEDICINE_EDITOR_FORM_FIELDS:
                self.fields.pop(field_name, None)

    def save(self, commit=True):
        obj = super().save(commit=commit)
        if obj.pk:
            attrs = dict(obj.extracted_attributes or {})
            seo_translations = dict(attrs.get("seo_translations") or {})
            seo_ru = dict(seo_translations.get("ru") or {})
            seo_en = dict(seo_translations.get("en") or attrs.get("seo_en") or {})
            # RU-поля формы — единственный редактируемый источник истины.
            # Без этой синхронизации apply предпочитал старый вложенный RU payload
            # и мог проигнорировать видимую правку модератора.
            seo_ru.update(
                {
                    "generated_title": (obj.generated_title or "").strip() or None,
                    "generated_description": (obj.generated_description or "").strip() or None,
                    "meta_title": (obj.generated_seo_title or "").strip() or None,
                    "meta_description": (obj.generated_seo_description or "").strip() or None,
                    "meta_keywords": obj.generated_keywords or [],
                }
            )
            if self.cleaned_data.get("generated_en_title") is not None:
                seo_en["generated_title"] = (self.cleaned_data.get("generated_en_title") or "").strip() or None
            if self.cleaned_data.get("generated_en_description") is not None:
                seo_en["generated_description"] = (self.cleaned_data.get("generated_en_description") or "").strip() or None
            if self.cleaned_data.get("og_title") is not None:
                seo_en["og_title"] = (self.cleaned_data.get("og_title") or "").strip() or None
            if self.cleaned_data.get("og_description") is not None:
                seo_en["og_description"] = (self.cleaned_data.get("og_description") or "").strip() or None
            seo_translations["ru"] = seo_ru
            seo_translations["en"] = seo_en
            attrs["seo_translations"] = seo_translations
            attrs["seo_en"] = seo_en
            product_type = getattr(getattr(obj, "product", None), "product_type", None)
            if "inventory_sizes" in self.cleaned_data and supports_size_inventory(product_type):
                moderator_sizes = parse_moderator_size_list(
                    self.cleaned_data.get("inventory_sizes"),
                    product_type,
                )
                attrs["moderator_sizes"] = moderator_sizes
                attrs["sizes"] = moderator_sizes
            # Атрибуты украшений
            for key, field_name in [
                ("jewelry_type", "jewelry_type"),
                ("material", "material"),
                ("metal_purity", "metal_purity"),
                ("stone_type", "stone_type"),
                ("carat_weight", "carat_weight"),
                ("gender", "gender"),
            ]:
                if field_name not in self.cleaned_data:
                    continue
                val = self.cleaned_data.get(field_name)
                if val is not None:
                    if val == "" or (isinstance(val, (int, float)) and val == 0 and key != "carat_weight"):
                        attrs[key] = None
                    else:
                        attrs[key] = val
            if product_type == "medicines":
                translations_data = dict(attrs.get("translations_data") or {})
                translations_ru = dict(translations_data.get("ru") or {})
                translations_en = dict(translations_data.get("en") or {})
                quality = dict(attrs.get("medicine_translation_quality") or {})
                decisions = dict(attrs.get("medicine_moderator_decisions") or {})
                overrides = dict(attrs.get("medicine_moderator_overrides") or {})
                preserved_locales = dict(
                    attrs.get("medicine_moderator_preserved_locales") or {}
                )
                for medicine_field in MEDICINE_EDITOR_FIELDS:
                    ru_field = _medicine_editor_field_name(medicine_field, "ru")
                    en_field = _medicine_editor_field_name(medicine_field, "en")
                    decision_field = _medicine_editor_field_name(medicine_field, "decision")
                    if decision_field not in self.cleaned_data:
                        continue
                    ru_value = str(self.cleaned_data.get(ru_field) or "").strip()
                    en_value = str(self.cleaned_data.get(en_field) or "").strip()
                    decision = self.cleaned_data.get(decision_field) or "apply"
                    initial = self._medicine_initial_values.get(medicine_field, {})
                    changed = (
                        ru_value != initial.get("ru", "")
                        or en_value != initial.get("en", "")
                        or decision != initial.get("decision", "apply")
                    )
                    if not changed:
                        continue
                    decisions[medicine_field] = decision
                    overrides[medicine_field] = {
                        "ru": ru_value,
                        "en": en_value,
                        "decision": decision,
                    }
                    if decision == "keep_current":
                        preserved_locales.pop(medicine_field, None)
                        continue
                    fallback_values = self._medicine_fallback_values.get(
                        medicine_field,
                        {},
                    )
                    used_fallback_locales = [
                        locale
                        for locale, value in fallback_values.items()
                        if decision == "merge_current"
                        and (ru_value if locale == "ru" else en_value) == value
                    ]
                    if used_fallback_locales:
                        preserved_locales[medicine_field] = used_fallback_locales
                    else:
                        preserved_locales.pop(medicine_field, None)
                    if ru_value:
                        translations_ru[medicine_field] = ru_value
                    else:
                        translations_ru.pop(medicine_field, None)
                    if en_value:
                        translations_en[medicine_field] = en_value
                    else:
                        translations_en.pop(medicine_field, None)
                    if medicine_field in MEDICINE_CLINICAL_FIELDS:
                        details = dict(quality.get(medicine_field) or {})
                        ru_complete = bool(ru_value) and not looks_untranslated_turkish(ru_value)
                        en_complete = bool(en_value)
                        details.update(
                            {
                                "ru_length": len(ru_value),
                                "en_length": len(en_value),
                                "ru_complete": ru_complete,
                                "en_complete": en_complete,
                                "complete": ru_complete and en_complete,
                                "moderator_reviewed": True,
                            }
                        )
                        quality[medicine_field] = details
                translations_data["ru"] = translations_ru
                translations_data["en"] = translations_en
                attrs["translations_data"] = translations_data
                attrs["medicine_translation_quality"] = quality
                attrs["medicine_moderator_decisions"] = decisions
                attrs["medicine_moderator_overrides"] = overrides
                attrs["medicine_moderator_preserved_locales"] = preserved_locales
            obj.extracted_attributes = attrs
            if commit:
                obj.save(update_fields=["extracted_attributes"])
        return obj


def _get_product_admin_url(product):
    """URL фактической доменной карточки для любого зарегистрированного типа."""
    if product is None:
        return None
    domain_obj = product.domain_item
    try:
        return reverse(
            f"admin:{domain_obj._meta.app_label}_{domain_obj._meta.model_name}_change",
            args=[domain_obj.pk],
        )
    except NoReverseMatch:
        return None


@admin.register(AIProcessingLog)
class AIProcessingLogAdmin(admin.ModelAdmin):
    form = AIProcessingLogForm
    change_list_template = "admin/ai/aiprocessinglog/change_list.html"
    change_form_template = "admin/ai/aiprocessinglog/change_form.html"
    # The production catalog contains thousands of products and categories.
    # Rendering all of them as <select> options on every log change page causes
    # large allocations in the already memory-constrained gunicorn workers.
    raw_id_fields = ("suggested_category",)
    list_display = (
        "view_log_link",
        "id",
        "product_link",
        "workflow_state",
        "application_state",
        "processing_type",
        "celery_task_id",
        "created_at",
        "completed_at",
        "tokens_total",
        "cost_usd",
        "llm_model",
    )
    list_filter = (
        "status",
        "application_status",
        "processing_type",
        "created_at",
        "processed_by",
        "llm_model",
    )
    search_fields = ("product__name", "generated_title", "error_message")
    list_select_related = ("product",)
    date_hierarchy = "created_at"
    readonly_fields = (
        "workflow_overview",
        "change_preview",
        "product",
        "status",
        "application_status",
        "application_report_view",
        "applied_at",
        "processed_by",
        "created_at",
        "updated_at",
        "completed_at",
        "moderation_date",
        "input_data",
        "image_urls_failed_warning",
        "formatted_llm_content",
        "raw_llm_response",
        "tokens_used",
        "cost_usd",
        "processing_time_ms",
        "stack_trace",
    )
    actions = (
        "apply_to_product",
        "reject_results",
        "rerun_ai_full",
        "rerun_ai_description_only",
    )

    def get_urls(self):
        """Keep rerun independent from validation of the editable log form."""
        custom_urls = [
            path(
                "<path:object_id>/rerun/",
                self.admin_site.admin_view(self.rerun_view),
                name="ai_aiprocessinglog_rerun",
            ),
        ]
        return custom_urls + super().get_urls()

    def rerun_view(self, request, object_id):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        obj = self.get_object(request, object_id)
        if obj is None:
            raise Http404("AI processing log does not exist")
        if not self.has_change_permission(request, obj):
            raise PermissionDenied
        return self._enqueue_rerun(request, obj)

    @admin.display(description="Celery task", ordering="created_at")
    def celery_task_id(self, obj):
        return str((obj.input_data or {}).get("celery_task_id") or "—")

    @admin.display(description="Состояние", ordering="status")
    def workflow_state(self, obj):
        title, tone = get_workflow_title(obj)
        colors = {
            "success": ("#166534", "#dcfce7"),
            "warning": ("#92400e", "#fef3c7"),
            "danger": ("#991b1b", "#fee2e2"),
            "info": ("#075985", "#e0f2fe"),
            "neutral": ("#374151", "#f3f4f6"),
        }
        foreground, background = colors.get(tone, colors["neutral"])
        return format_html(
            '<span style="display:inline-block;padding:3px 8px;border-radius:999px;'
            'font-weight:600;color:{};background:{};">{}</span>',
            foreground,
            background,
            title,
        )

    @admin.display(description="Применение", ordering="application_status")
    def application_state(self, obj):
        if (
            obj.application_status == AIApplicationStatus.PARTIAL
            and (obj.application_report or {}).get("product_updated") is False
        ):
            return "Товар не изменён; есть нерешённые поля"
        return APPLICATION_LABELS.get(obj.application_status, obj.get_application_status_display())

    fieldsets = (
        (
            "Состояние и товар",
            {
                "fields": (
                    "workflow_overview",
                    "product",
                    "processing_type",
                    "status",
                    "application_status",
                    "processed_by",
                    "moderation_date",
                    "applied_at",
                ),
            },
        ),
        (
            "Что изменится в товаре",
            {
                "fields": ("change_preview",),
                "description": (
                    "Сравнение строится по фактической доменной карточке товара. "
                    "Заблокированные поля сервис применения не запишет."
                ),
            },
        ),
        (
            "Контент на русском",
            {
                "fields": (
                    "generated_title",
                    "generated_description",
                ),
                "description": "Можно исправить предложение AI перед применением.",
            },
        ),
        (
            "Категория",
            {
                "fields": (
                    "suggested_category",
                    "category_confidence",
                    "category_alternatives",
                ),
                "description": "Категория применяется только при уверенности не ниже 75%.",
            },
        ),
        (
            "SEO на русском",
            {
                "fields": (
                    "generated_seo_title",
                    "generated_seo_description",
                    "generated_keywords",
                )
            },
        ),
        (
            "Контент и SEO на английском",
            {
                "fields": (
                    "generated_en_title",
                    "generated_en_description",
                    "og_title",
                    "og_description",
                ),
                "description": "Эти поля попадут в перевод EN и SEO/OG карточки.",
            },
        ),
        (
            "Исправление медицинских разделов RU/EN",
            {
                "fields": MEDICINE_CLINICAL_EDITOR_ROWS,
                "description": (
                    "Исправьте языковые версии до применения. Если AI пропустил RU или EN, "
                    "форма подставит подходящее текущее значение товара и предложит сохранить "
                    "его вместе с новым переводом. После сохранения проверка будет пересчитана. "
                    "Этот блок отображается только для лекарств."
                ),
            },
        ),
        (
            "Остальные медицинские поля RU/EN",
            {
                "classes": ("collapse",),
                "fields": MEDICINE_DETAIL_EDITOR_ROWS,
                "description": (
                    "Локализованные атрибуты препарата. Ручные правки сохраняются в AI-логе "
                    "и используются при следующем применении."
                ),
            },
        ),
        (
            "Размеры и наличие",
            {
                "fields": ("inventory_sizes",),
                "description": (
                    "Размеры хранятся в отдельных полях карточки и не попадут в описание. "
                    "Если у товара есть варианты, применение будет остановлено до выбора варианта."
                ),
            },
        ),
        (
            "Атрибуты украшения (применяются к карточке товара)",
            {
                "fields": (
                    "jewelry_type",
                    "material",
                    "metal_purity",
                    "stone_type",
                    "carat_weight",
                    "gender",
                ),
                "description": "Этот блок отображается только для товаров типа «Украшения».",
            },
        ),
        (
            "Решение модератора",
            {
                "fields": ("moderation_notes",),
                "description": (
                    "Оставьте пояснение для коллег. Основная кнопка одновременно сохранит правки, "
                    "применит разрешённые поля и закроет очередь при полном успехе."
                ),
            },
        ),
        (
            "Извлечённые атрибуты (JSON)",
            {
                "classes": ("collapse",),
                "fields": ("extracted_attributes",),
                "description": (
                    "Техническое редактирование атрибутов для всех категорий. "
                    "Итоговые значения показаны в таблице сравнения выше."
                ),
            },
        ),
        (
            "Анализ изображений",
            {
                "classes": ("collapse",),
                "fields": ("input_images_urls", "image_urls_failed_warning", "image_analysis"),
            },
        ),
        (
            "Технические метрики",
            {
                "classes": ("collapse",),
                "fields": (
                    "llm_model",
                    "tokens_used",
                    "cost_usd",
                    "processing_time_ms",
                    "created_at",
                    "completed_at",
                    "updated_at",
                    "application_report_view",
                ),
            },
        ),
        (
            "Исходный ответ AI",
            {
                "classes": ("collapse",),
                "fields": ("formatted_llm_content",),
                "description": (
                    "Только для сверки. Источником применения служат редактируемые поля выше."
                ),
            },
        ),
        (
            "Отладка (сырой ответ и ошибки)",
            {
                "classes": ("collapse",),
                "fields": (
                    "input_data",
                    "raw_llm_response",
                    "error_message",
                    "stack_trace",
                ),
                "description": "Если «Результаты генерации» и «SEO» пустые — откройте raw_llm_response и проверьте формат ответа модели.",
            },
        ),
    )

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj))
        product_type = getattr(getattr(obj, "product", None), "product_type", None)
        if product_type != "jewelry":
            fieldsets = [
                fieldset
                for fieldset in fieldsets
                if fieldset[0] != "Атрибуты украшения (применяются к карточке товара)"
            ]
        if product_type != "medicines":
            fieldsets = [
                fieldset
                for fieldset in fieldsets
                if fieldset[0]
                not in {
                    "Исправление медицинских разделов RU/EN",
                    "Остальные медицинские поля RU/EN",
                }
            ]
        if not supports_size_inventory(product_type):
            fieldsets = [
                fieldset for fieldset in fieldsets if fieldset[0] != "Размеры и наличие"
            ]
        return fieldsets

    @admin.display(description="Итог обработки")
    def workflow_overview(self, obj):
        if not obj or not obj.pk:
            return "—"
        title, tone = get_workflow_title(obj)
        colors = {
            "success": ("#166534", "#dcfce7", "#86efac"),
            "warning": ("#92400e", "#fef3c7", "#fcd34d"),
            "danger": ("#991b1b", "#fee2e2", "#fca5a5"),
            "info": ("#075985", "#e0f2fe", "#7dd3fc"),
            "neutral": ("#374151", "#f3f4f6", "#d1d5db"),
        }
        foreground, background, border = colors.get(tone, colors["neutral"])
        reasons = []
        if obj.status in (AIProcessingStatus.COMPLETED, AIProcessingStatus.MODERATION):
            try:
                semantic_report = self._semantic_report(obj)
                reasons = get_moderation_reason_labels(
                    obj,
                    semantic_report=semantic_report,
                )
                rejected_labels = get_rejected_field_labels(
                    sorted(semantic_report.rejected_fields)
                )
                if rejected_labels:
                    reasons.insert(
                        0,
                        "Не будут применены: " + ", ".join(rejected_labels),
                    )
                medicine_details = get_incomplete_medicine_field_messages(
                    obj,
                    semantic_report.rejected_fields,
                )
                if medicine_details:
                    reasons[1:1] = medicine_details
            except Exception as exc:
                reasons = [f"Не удалось рассчитать причины: {exc}"]
        product_url = _get_product_admin_url(obj.product)
        product_link = escape(obj.product.name)
        if product_url:
            product_link = (
                f'<a href="{escape(product_url)}" target="_blank" rel="noopener" '
                f'style="font-weight:700;">{escape(obj.product.name)} ↗</a>'
            )
        reason_html = ""
        if reasons:
            reason_html = (
                '<ul style="margin:8px 0 0 18px;">'
                + "".join(f"<li>{escape(reason)}</li>" for reason in reasons)
                + "</ul>"
            )
        application_label = APPLICATION_LABELS.get(
            obj.application_status,
            obj.get_application_status_display(),
        )
        if (
            obj.application_status == AIApplicationStatus.PARTIAL
            and (obj.application_report or {}).get("product_updated") is False
        ):
            application_label = "Товар не изменён; есть нерешённые поля"
        return mark_safe(
            f'<div class="ai-workflow-card" style="padding:14px 16px;border:1px solid {border};'
            f'border-left:5px solid {border};background:{background};color:{foreground};'
            'border-radius:6px;max-width:1100px;">'
            f'<div style="font-size:17px;font-weight:800;">{escape(title)}</div>'
            f'<div style="margin-top:6px;color:inherit;">Товар: {product_link}</div>'
            f'<div style="margin-top:3px;color:inherit;">Тип: '
            f'{escape(obj.product.get_product_type_display())} · Применение: '
            f'<strong>{escape(application_label)}</strong></div>'
            f'{reason_html}</div>'
        )

    @admin.display(description="Сравнение текущего товара и результата AI")
    def change_preview(self, obj):
        if not obj or not obj.pk:
            return "—"
        try:
            rows = build_change_preview(
                obj,
                semantic_report=self._semantic_report(obj),
            )
        except Exception as exc:
            return format_html(
                '<div style="color:#991b1b;background:#fee2e2;padding:10px;border-radius:4px;">'
                "Не удалось построить сравнение: {}</div>",
                str(exc),
            )
        if not rows:
            return mark_safe(
                '<div style="padding:10px;background:#f3f4f6;border-radius:4px;">'
                "AI не предложил полей, которые поддерживает текущий обработчик товара.</div>"
            )
        decision_colors = {
            "apply": ("#166534", "#dcfce7"),
            "unchanged": ("#374151", "#f3f4f6"),
            "blocked": ("#991b1b", "#fee2e2"),
            "preserved": ("#92400e", "#fef3c7"),
            "empty": ("#6b7280", "#f9fafb"),
        }
        body = []
        previous_section = None
        hide_unchanged = getattr(obj.product, "product_type", None) == "medicines"
        unchanged_count = sum(row.decision == "unchanged" for row in rows)
        changed_count = sum(row.decision == "apply" for row in rows)
        blocked_count = sum(row.decision == "blocked" for row in rows)
        table_id = f"ai-preview-{obj.pk}"
        section_decisions = {}
        for preview_row in rows:
            section_decisions.setdefault(preview_row.section, []).append(preview_row.decision)
        for row in rows:
            if row.section != previous_section:
                section_hidden = (
                    hide_unchanged
                    and all(
                        decision == "unchanged"
                        for decision in section_decisions.get(row.section, [])
                    )
                )
                section_class = "ai-preview-unchanged" if section_hidden else "ai-preview-section"
                section_style = "display:none;" if section_hidden else ""
                body.append(
                    f'<tr class="ai-preview-section {section_class}" style="{section_style}"><th colspan="4" '
                    'style="text-align:left;padding:9px 10px;background:#e5e7eb;color:#111827;">'
                    f'{escape(row.section)}</th></tr>'
                )
                previous_section = row.section
            foreground, background = decision_colors.get(
                row.decision,
                decision_colors["unchanged"],
            )
            reason = (
                f'<div style="font-size:11px;margin-top:3px;">{escape(row.reason)}</div>'
                if row.reason
                else ""
            )
            row_hidden = hide_unchanged and row.decision == "unchanged"
            row_class = "ai-preview-unchanged" if row_hidden else ""
            row_style = "display:none;" if row_hidden else ""
            body.append(
                f'<tr class="{row_class}" style="{row_style}">'
                f'<td style="font-weight:650;min-width:150px;">{escape(row.label)}</td>'
                f'<td><div class="ai-preview-value">{escape(row.current)}</div></td>'
                f'<td><div class="ai-preview-value">{escape(row.proposed)}</div></td>'
                f'<td><span style="display:inline-block;padding:3px 7px;border-radius:999px;'
                f'font-weight:650;color:{foreground};background:{background};">'
                f'{escape(row.decision_label)}</span>{reason}</td>'
                "</tr>"
            )
        toggle = ""
        if hide_unchanged and unchanged_count:
            toggle = (
                f'<button type="button" class="button" style="margin-left:8px;" '
                f'onclick="var rows=document.querySelectorAll(\'#{table_id} .ai-preview-unchanged\');'
                "var show=Array.prototype.some.call(rows,function(row){return row.style.display===\'none\';});"
                "Array.prototype.forEach.call(rows,function(row){row.style.display=show?\'table-row\':\'none\';});"
                f'this.textContent=show?\'Скрыть неизменённые ({unchanged_count})\':\'Показать неизменённые ({unchanged_count})\';">'
                f'Показать неизменённые ({unchanged_count})</button>'
            )
        summary = (
            '<div style="margin:0 0 10px;padding:8px 10px;background:#f3f4f6;border-radius:4px;">'
            f'<strong>Будет изменено: {changed_count}</strong> · '
            f'Заблокировано: {blocked_count} · Без изменений: {unchanged_count}{toggle}</div>'
        )
        return mark_safe(
            summary
            +
            '<div class="ai-preview-wrap" style="overflow-x:auto;max-width:1200px;">'
            f'<table id="{table_id}" class="ai-preview-table" style="width:100%;border-collapse:collapse;">'
            '<thead><tr><th>Поле</th><th>Сейчас в товаре</th><th>Предложение AI</th>'
            '<th>Что произойдёт</th></tr></thead><tbody>'
            + "".join(body)
            + "</tbody></table></div>"
        )

    @staticmethod
    def _semantic_report(obj):
        """Calculate semantic validation once for all read-only admin blocks."""
        cache_attr = "_ai_admin_semantic_report"
        report = getattr(obj, cache_attr, None)
        if report is None:
            from .services.semantic_validator import SemanticValidator

            report = SemanticValidator().validate_log(obj)
            setattr(obj, cache_attr, report)
        return report

    @admin.display(description="Последний отчёт применения")
    def application_report_view(self, obj):
        if not obj or not obj.application_report:
            return "—"
        return format_html(
            '<pre style="white-space:pre-wrap;max-height:260px;overflow:auto;">{}</pre>',
            json.dumps(obj.application_report, ensure_ascii=False, indent=2),
        )

    def formatted_llm_content(self, obj):
        """
        Показывает ответ LLM в удобном для человека виде: секции RU/EN/SEO/категория,
        затем полный JSON в сворачиваемом блоке. Редактировать нужно поля выше (результаты, SEO).
        """
        if not obj or not obj.raw_llm_response:
            return mark_safe("<p>Ответ модели ещё не получен или пуст.</p>")
        raw = obj.raw_llm_response
        content = raw.get("content") if isinstance(raw, dict) else raw
        if content is None:
            content = raw
        if not isinstance(content, dict):
            try:
                content = json.loads(content) if isinstance(content, str) else {"_raw": str(content)}
            except (TypeError, ValueError):
                content = {"_raw": str(content)[:2000]}
        parts = []
        # Секция RU
        ru = content.get("ru") or content
        if isinstance(ru, dict):
            ru_title = ru.get("generated_title") or ""
            ru_desc = ru.get("generated_description") or ""
            if ru_title or ru_desc:
                parts.append(
                    '<div class="formatted-llm-section" style="margin-bottom: 1em;">'
                    '<strong style="color: #0c5460;">Русский (ru)</strong>'
                    '<div style="margin-left: 0.5em; margin-top: 0.25em;">'
                    f'<div><strong>Заголовок:</strong> {escape(ru_title) or "—"}</div>'
                    f'<div><strong>Описание:</strong><div class="formatted-llm-block" style="white-space: pre-wrap; max-height: 200px; overflow: auto; background: #f8f9fa; padding: 0.5em; border-radius: 4px; margin-top: 0.25em;">{escape(ru_desc) or "—"}</div></div>'
                    "</div></div>"
                )
        # Секция EN
        en = content.get("en")
        if isinstance(en, dict):
            en_title = en.get("generated_title") or ""
            en_desc = en.get("generated_description") or ""
            seo_title = en.get("seo_title") or ""
            seo_desc = en.get("seo_description") or ""
            keywords = en.get("keywords") or []
            kw_str = ", ".join(str(x) for x in keywords if x)[:500] if keywords else "—"
            if any([en_title, en_desc, seo_title, seo_desc, kw_str != "—"]):
                parts.append(
                    '<div class="formatted-llm-section" style="margin-bottom: 1em;">'
                    '<strong style="color: #0c5460;">English (en)</strong>'
                    '<div style="margin-left: 0.5em; margin-top: 0.25em;">'
                    f'<div><strong>Title:</strong> {escape(en_title) or "—"}</div>'
                    f'<div><strong>Description:</strong><div class="formatted-llm-block" style="white-space: pre-wrap; max-height: 200px; overflow: auto; background: #f8f9fa; padding: 0.5em; border-radius: 4px; margin-top: 0.25em;">{escape(en_desc) or "—"}</div></div>'
                    f'<div><strong>SEO title:</strong> {escape(seo_title) or "—"}</div>'
                    f'<div><strong>SEO description:</strong> {escape(seo_desc) or "—"}</div>'
                    f'<div><strong>Keywords:</strong> {escape(kw_str)}</div>'
                    "</div></div>"
                )
        # Категория
        cat_name = content.get("suggested_category_name") or ""
        conf = content.get("category_confidence")
        if cat_name or conf is not None:
            parts.append(
                '<div class="formatted-llm-section" style="margin-bottom: 1em;">'
                '<strong style="color: #0c5460;">Категория</strong>'
                f'<div style="margin-left: 0.5em;">{escape(cat_name) or "—"}'
                f'{f" (уверенность: {conf})" if conf is not None else ""}</div></div>'
            )
        # Атрибуты
        attrs = content.get("attributes")
        if isinstance(attrs, dict) and attrs:
            attrs_str = json.dumps(attrs, ensure_ascii=False, indent=2)
            parts.append(
                '<div class="formatted-llm-section" style="margin-bottom: 1em;">'
                '<strong style="color: #0c5460;">Атрибуты</strong>'
                f'<pre class="formatted-llm-block" style="white-space: pre-wrap; max-height: 150px; overflow: auto; background: #f8f9fa; padding: 0.5em; border-radius: 4px; font-size: 12px;">{escape(attrs_str)}</pre></div>'
            )
        if not parts:
            parts.append("<p>В ответе нет распознанных полей ru/en/SEO. См. полный JSON ниже.</p>")
        # Полный JSON в сворачиваемом блоке
        try:
            json_str = json.dumps(content, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            json_str = str(content)
        parts.append(
            '<details style="margin-top: 0.5em;">'
            '<summary style="cursor: pointer; color: #0c5460;">Полный JSON ответа</summary>'
            f'<pre class="formatted-llm-block" style="white-space: pre-wrap; max-height: 400px; overflow: auto; background: #f1f3f4; padding: 0.75em; border-radius: 4px; font-size: 12px; margin-top: 0.25em;">{escape(json_str)}</pre>'
            "</details>"
        )
        return mark_safe("<div class=\"formatted-llm-content\">" + "".join(parts) + "</div>")

    formatted_llm_content.short_description = "Ответ LLM (читабельный вид)"

    def change_view(self, request, object_id, form_url="", extra_context=None):
        """Добавить контекст однозначных действий модератора."""
        extra_context = extra_context or {}
        obj = self.get_object(request, object_id)
        if obj is not None:
            extra_context.update(
                {
                    "can_review_and_apply": obj.status
                    in (
                        AIProcessingStatus.COMPLETED,
                        AIProcessingStatus.MODERATION,
                        AIProcessingStatus.APPROVED,
                    ),
                    "can_reject_result": obj.status
                    in (AIProcessingStatus.COMPLETED, AIProcessingStatus.MODERATION),
                    "can_rerun_ai": obj.status
                    not in (AIProcessingStatus.PENDING, AIProcessingStatus.PROCESSING),
                    "is_reapply": obj.status == AIProcessingStatus.APPROVED,
                    "product_admin_url": _get_product_admin_url(obj.product),
                    "rerun_url": reverse(
                        "admin:ai_aiprocessinglog_rerun",
                        args=[obj.pk],
                    ),
                }
            )
        return super().change_view(request, object_id, form_url, extra_context)

    def response_change(self, request, obj):
        """Обработать review/apply, reject и re-run из формы лога."""
        if "_save_and_apply" in request.POST:
            if obj.status not in (
                AIProcessingStatus.COMPLETED,
                AIProcessingStatus.MODERATION,
                AIProcessingStatus.APPROVED,
            ):
                messages.warning(
                    request,
                    f"Лог #{obj.id}: применение невозможно — статус «{obj.get_status_display()}». "
                    "Нужен завершённый, проверяемый или уже применённый результат.",
                )
                return self._response_post_save(request, obj)
            try:
                from .services.content_generator import ContentGenerator
                gen = ContentGenerator()
                gen.apply_log_to_product(
                    obj,
                    user=request.user,
                    allow_approved=True,
                )
                if obj.application_status == AIApplicationStatus.PARTIAL:
                    rejected = (obj.application_report or {}).get("rejected_fields") or []
                    rejected_labels = ", ".join(get_rejected_field_labels(rejected))
                    updated = bool((obj.application_report or {}).get("product_updated"))
                    applied_message = (
                        "Разрешённые изменения перенесены."
                        if updated
                        else "Товар не изменён."
                    )
                    medicine_details = get_incomplete_medicine_field_messages(
                        obj,
                        rejected,
                    )
                    detail_message = (
                        " " + " ".join(medicine_details)
                        if medicine_details
                        else ""
                    )
                    messages.warning(
                        request,
                        f"Лог #{obj.id}: {applied_message} "
                        f"Не перенесены: {rejected_labels or 'поля, требующие проверки'}. "
                        f"{detail_message} "
                        "Запись остаётся на модерации; отдельное предварительное "
                        "одобрение не требуется. Исправьте недостающий язык или выберите "
                        "сохранение текущего языка товара.",
                    )
                else:
                    kept_fields = (obj.application_report or {}).get(
                        "moderator_kept_fields"
                    ) or []
                    kept_note = ""
                    if kept_fields:
                        kept_note = (
                            " По решению модератора сохранены текущими: "
                            + ", ".join(get_rejected_field_labels(
                                [f"medicine_translation:{field}" for field in kept_fields]
                            ))
                            + "."
                        )
                    preserved_locales = (obj.application_report or {}).get(
                        "moderator_preserved_locales"
                    ) or {}
                    preserved_note = ""
                    if preserved_locales:
                        preserved_parts = []
                        for field_name, locales in preserved_locales.items():
                            label = MEDICINE_TRANSLATION_FIELD_LABELS.get(
                                field_name,
                                field_name,
                            ).removesuffix(" RU/EN")
                            preserved_parts.append(
                                f"{label}: текущий {'/'.join(locale.upper() for locale in locales)}"
                            )
                        preserved_note = (
                            " Сохранены существующие языковые версии товара: "
                            + "; ".join(preserved_parts)
                            + "."
                        )
                    updated = bool((obj.application_report or {}).get("product_updated"))
                    result_text = (
                        f"проверено и применено к товару «{obj.product.name}»"
                        if updated
                        else f"проверено; товар «{obj.product.name}» уже содержит выбранные значения"
                    )
                    messages.success(
                        request,
                        f"Лог #{obj.id}: {result_text}. "
                        f"Очередь модерации закрыта.{kept_note}{preserved_note}",
                    )
            except Exception as e:
                messages.error(request, f"Ошибка при применении: {e}")
            return self._response_post_save(request, obj)
        if "_reject_result" in request.POST:
            try:
                reject_log(
                    obj,
                    user=request.user,
                    notes=obj.moderation_notes or "",
                )
                messages.success(request, f"Лог #{obj.id}: результат отклонён.")
            except ValueError as exc:
                messages.warning(request, str(exc))
            return self._response_post_save(request, obj)
        if "_rerun_ai" in request.POST:
            return self._enqueue_rerun(request, obj)
        return super().response_change(request, obj)

    def _enqueue_rerun(self, request, obj):
        from .tasks import enqueue_product_ai_task

        try:
            queued_log, _task_id, submitted = enqueue_product_ai_task(
                product_id=obj.product_id,
                processing_type=obj.processing_type,
                auto_apply=False,
                force=True,
            )
            if submitted:
                messages.success(
                    request,
                    f"Создан новый AI-лог #{queued_log.id}; открыта его страница. "
                    "Результат не будет применён автоматически.",
                )
                return HttpResponseRedirect(
                    reverse("admin:ai_aiprocessinglog_change", args=[queued_log.id])
                )
            else:
                messages.warning(
                    request,
                    f"AI-лог #{queued_log.id} уже находится в очереди или обрабатывается; "
                    "открыта его страница.",
                )
                return HttpResponseRedirect(
                    reverse("admin:ai_aiprocessinglog_change", args=[queued_log.id])
                )
        except Exception as exc:
            messages.error(request, f"Не удалось перезапустить AI: {exc}")
        return self._response_post_save(request, obj)

    def _response_post_save(self, request, obj):
        """Редирект обратно на форму после сохранения."""
        return HttpResponseRedirect(
            reverse("admin:ai_aiprocessinglog_change", args=[obj.pk])
        )

    def view_log_link(self, obj):
        """Ссылка на форму лога (результаты AI). Клик сюда — просмотр и применение."""
        if obj.pk:
            url = reverse("admin:ai_aiprocessinglog_change", args=[obj.pk])
            return format_html(
                '<a href="{}" style="font-weight: bold;">Просмотр / применить</a>',
                url,
            )
        return "-"

    view_log_link.short_description = "Результаты AI"

    def product_link(self, obj):
        if obj.product:
            url = _get_product_admin_url(obj.product)
            name = obj.product.name
            if url:
                return format_html(
                    '{} <a href="{}" style="font-size:11px;color:#999;">→ товар</a>',
                    escape(name),
                    url,
                )
            return name
        return "-"

    product_link.short_description = "Товар"

    def tokens_total(self, obj):
        tokens = obj.tokens_used or {}
        return tokens.get("total") or tokens.get("total_tokens") or 0

    tokens_total.short_description = "Токены"

    def image_urls_failed_warning(self, obj):
        """Предупреждение о недоступных ссылках на изображения."""
        if not obj or not obj.input_data:
            return ""
        failed = obj.input_data.get("image_urls_failed") or []
        if not failed:
            return ""
        lines = [f"Не удалось загрузить {len(failed)} изображений (ссылки не работают или не изображения):"]
        for u in failed[:10]:
            lines.append(f"• {u[:120]}{'…' if len(u) > 120 else ''}")
        if len(failed) > 10:
            lines.append(f"… и ещё {len(failed) - 10}.")
        return format_html(
            '<div style="background:#fef3c7;padding:8px;border-radius:4px;color:#92400e;">{}</div>',
            mark_safe("<br>".join(escape(ln) for ln in lines)),
        )

    image_urls_failed_warning.short_description = "Предупреждение: недоступные изображения"

    def apply_to_product(self, request, queryset):
        """Проверить и применить результат AI к товару."""
        from .services.content_generator import ContentGenerator
        gen = ContentGenerator()
        applied = 0
        partial = 0
        partial_details = []
        auto_preserved_details = []
        skipped = 0
        for log in queryset:
            if log.status not in (
                AIProcessingStatus.COMPLETED,
                AIProcessingStatus.MODERATION,
                AIProcessingStatus.APPROVED,
            ):
                skipped += 1
                continue
            if not log.product_id:
                skipped += 1
                continue
            try:
                preserved = _persist_medicine_current_translation_fallbacks(log)
                if preserved:
                    preserved_parts = []
                    for field_name, locales in preserved.items():
                        label = MEDICINE_TRANSLATION_FIELD_LABELS.get(
                            field_name,
                            field_name,
                        ).removesuffix(" RU/EN")
                        preserved_parts.append(
                            f"{label}: текущий {'/'.join(locale.upper() for locale in locales)}"
                        )
                    auto_preserved_details.append(
                        f"#{log.id} — " + "; ".join(preserved_parts)
                    )
                gen.apply_log_to_product(
                    log,
                    user=request.user,
                    allow_approved=True,
                )
                if log.application_status == AIApplicationStatus.PARTIAL:
                    partial += 1
                    rejected = (log.application_report or {}).get("rejected_fields") or []
                    labels = ", ".join(get_rejected_field_labels(rejected))
                    medicine_details = get_incomplete_medicine_field_messages(
                        log,
                        rejected,
                    )
                    detail = " ".join(medicine_details)
                    partial_details.append(
                        f"#{log.id} — {labels or 'поля, требующие проверки'}"
                        + (f": {detail}" if detail else "")
                    )
                else:
                    applied += 1
            except Exception as e:
                messages.error(
                    request,
                    f"Лог #{log.id}: не удалось применить — {e}",
                )
        preserved_note = ""
        if auto_preserved_details:
            preserved_note = (
                " Сохранены существующие языковые версии товара: "
                + "; ".join(auto_preserved_details[:5])
                + ("; …" if len(auto_preserved_details) > 5 else "")
                + "."
            )
        if applied:
            messages.success(
                request,
                f"Проверено и полностью применено к товарам: {applied}."
                f"{preserved_note}",
            )
        if partial:
            visible_details = "; ".join(partial_details[:5])
            if len(partial_details) > 5:
                visible_details += "; …"
            messages.warning(
                request,
                f"Не полностью обработано AI-логов: {partial}. {visible_details}. "
                "Если товар не изменён, это указано в самом логе. Записи остаются на "
                "модерации только до решения по перечисленным полям."
                f"{preserved_note}",
            )
        if skipped:
            messages.info(request, f"Пропущено логов с неподходящим статусом: {skipped}.")

    apply_to_product.short_description = "Проверено — применить к товару"

    def reject_results(self, request, queryset):
        rejected = 0
        skipped = 0
        for log in queryset.select_related("product"):
            try:
                reject_log(log, user=request.user)
                rejected += 1
            except ValueError:
                skipped += 1
        if rejected:
            messages.success(request, f"Отклонено результатов: {rejected}.")
        if skipped:
            messages.info(request, f"Пропущено логов с неподходящим статусом: {skipped}.")

    reject_results.short_description = "Отклонить результат"

    def rerun_ai_full(self, request, queryset):
        from .tasks import enqueue_product_ai_task

        product_ids = list(
            queryset.values_list("product_id", flat=True).distinct()
        )
        for product_id in product_ids:
            enqueue_product_ai_task(
                product_id=product_id,
                processing_type="full",
                auto_apply=False,
                force=True,
            )
        messages.success(
            request,
            f"Запущена AI обработка (full) для {len(product_ids)} товаров. "
            "Результаты появятся в логах; применить к товару — вручную после проверки.",
        )

    rerun_ai_full.short_description = (
        "Перезапустить AI (full) по товарам"
    )

    def rerun_ai_description_only(self, request, queryset):
        from .tasks import enqueue_product_ai_task

        product_ids = list(
            queryset.values_list("product_id", flat=True).distinct()
        )
        for product_id in product_ids:
            enqueue_product_ai_task(
                product_id=product_id,
                processing_type="description_only",
                auto_apply=False,
                force=True,
            )
        message = (
            "Запущена AI обработка (description_only) для "
            f"{len(product_ids)} товаров. Результаты в логах; применить — вручную после проверки."
        )
        messages.success(request, message)

    rerun_ai_description_only.short_description = (
        "Перезапустить AI (description_only) по товарам"
    )

@admin.register(AITemplate)
class AITemplateAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "template_type",
        "language",
        "category",
        "is_active",
        "usage_count",
        "success_rate",
        "updated_at",
    )
    list_filter = ("template_type", "is_active", "language", "category")
    search_fields = ("name", "content")
    readonly_fields = (
        "usage_count",
        "success_rate",
        "created_at",
        "updated_at",
    )
    list_select_related = ("category",)


@admin.register(AIModerationQueue)
class AIModerationQueueAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "log_link",
        "product_link",
        "log_status",
        "application_state",
        "priority",
        "human_reason",
        "assigned_to",
        "created_at",
        "resolved_at",
    )
    list_filter = (
        "priority",
        "created_at",
        "assigned_to",
        "reason",
        ("resolved_at", admin.EmptyFieldListFilter),
    )
    list_select_related = (
        "log_entry",
        "assigned_to",
        "log_entry__product",
    )
    date_hierarchy = "created_at"
    actions = (
        "set_priority_low",
        "set_priority_medium",
        "set_priority_high",
    )

    def log_link(self, obj):
        return format_html(
            '<a href="/admin/ai/aiprocessinglog/{}/change/" style="font-weight:700;">'
            "Проверить результат #{}</a>",
            obj.log_entry.id,
            obj.log_entry.id,
        )

    log_link.short_description = "Лог обработки"

    def product_link(self, obj):
        product = getattr(obj.log_entry, "product", None)
        if product:
            url = _get_product_admin_url(product)
            if url:
                return format_html(
                    '<a href="{}">{}</a>',
                    url,
                    product.name,
                )
            return product.name
        return "-"

    product_link.short_description = "Товар"

    @admin.display(description="Состояние AI", ordering="log_entry__status")
    def log_status(self, obj):
        title, _tone = get_workflow_title(obj.log_entry)
        return title

    @admin.display(description="Применение", ordering="log_entry__application_status")
    def application_state(self, obj):
        return APPLICATION_LABELS.get(
            obj.log_entry.application_status,
            obj.log_entry.get_application_status_display(),
        )

    @admin.display(description="Причина", ordering="reason")
    def human_reason(self, obj):
        from .services.moderation import MODERATION_REASON_LABELS

        return MODERATION_REASON_LABELS.get(obj.reason, obj.reason)

    def set_priority_low(self, request, queryset):
        updated = queryset.update(priority=1)
        messages.success(request, f"Приоритет: низкий ({updated})")

    set_priority_low.short_description = "Приоритет: низкий"

    def set_priority_medium(self, request, queryset):
        updated = queryset.update(priority=2)
        messages.success(request, f"Приоритет: средний ({updated})")

    set_priority_medium.short_description = "Приоритет: средний"

    def set_priority_high(self, request, queryset):
        updated = queryset.update(priority=3)
        messages.success(request, f"Приоритет: высокий ({updated})")

    set_priority_high.short_description = "Приоритет: высокий"
