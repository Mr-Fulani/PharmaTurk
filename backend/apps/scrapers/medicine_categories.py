"""Medicine import safeguards and opt-in refinement; no saves or source requests."""

import re

from django.conf import settings

from apps.catalog.medicine_taxonomy import propose_medicine_category
from apps.catalog.models import Category, MedicineProduct


class MedicineCategoryConflict(Exception):
    """An ambiguous medicine import requires review instead of partial writes."""


def _mapping(value):
    return value if isinstance(value, dict) else {}


def merge_medicine_attributes(previous, fresh):
    """Omitted/empty sections never erase previously parsed useful content."""
    merged = dict(_mapping(previous))
    for key, value in _mapping(fresh).items():
        if value is None or value == "" or value == [] or value == {}:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        merged[key] = (
            merge_medicine_attributes(merged.get(key), value)
            if isinstance(value, dict) else value
        )
    return merged


def _normalized(value, field):
    value = str(value or "").strip()
    if field == "atc_code":
        return tuple(sorted(set(re.split(r"\s*[/,;|+]\s*", value.upper())))) if value else ()
    if field == "active_ingredient":
        return " ".join(value.casefold().split())
    return value


def _validate_identity(scraped, existing, medicine):
    """All populated copies must agree before any price/content/category write.

    Missing fields are not conflicts or deletion instructions. Do not reconcile
    a source/domain/JSON mismatch by picking one of the existing representations.
    """
    attrs = _mapping(scraped.attributes)
    stored = [_mapping(_mapping(existing.external_data).get("attributes"))]
    if medicine is not None:
        stored.append(_mapping(_mapping(medicine.external_data).get("attributes")))
    for field in ("barcode", "atc_code", "active_ingredient"):
        values = [attrs.get(field), *(data.get(field) for data in stored)]
        if medicine is not None:
            values.append(getattr(medicine, field))
        if field == "barcode":
            values.append(scraped.barcode)
        known = {_normalized(value, field) for value in values if str(value or "").strip()}
        if len(known) > 1:
            raise MedicineCategoryConflict(f"{field}_conflict")


def validate_existing_medicine(scraped, existing, *, is_variant_update=False):
    if is_variant_update or existing.product_type != "medicines":
        raise MedicineCategoryConflict("variant_or_product_type_conflict")
    attrs = _mapping(scraped.attributes)
    if attrs.get("is_stub") is True:
        raise MedicineCategoryConflict("incomplete_source_card")
    medicine = (
        MedicineProduct.objects.filter(base_product_id=existing.pk)
        .select_related("category").first()
    )
    data = [attrs, _mapping(existing.external_data)]
    if medicine is not None:
        data.append(_mapping(medicine.external_data))
    data += [_mapping(value.get("attributes")) for value in data]
    if any(value.get(key) for value in data
           for key in ("source_variant_id", "source_variant_slug")):
        raise MedicineCategoryConflict("variant_requires_review")
    _validate_identity(scraped, existing, medicine)
    return medicine


def validate_new_medicine(scraped):
    attrs = _mapping(scraped.attributes)
    if scraped.barcode and attrs.get("barcode"):
        if str(scraped.barcode).strip() != str(attrs["barcode"]).strip():
            raise MedicineCategoryConflict("barcode_conflict")


def prepare_medicine_category_mapping(session, scraped):
    """A task root outranks config defaults, but is not a forced leaf override."""
    scraped.__dict__.pop("_medicine_category_root", None)
    scraped.__dict__.pop("_medicine_import_skip_reason", None)
    scraped.__dict__.pop("_medicine_media_deferred", None)
    if str(scraped.source or "").strip().lower() != "ilacfiyati":
        return False
    category = session.target_category or session.scraper_config.default_category
    if not category or category.slug != "medicines" or category.parent_id is not None:
        return False
    scraped.__dict__.pop("_category_override", None)
    scraped._medicine_category_root = category
    scraped.category = category.slug
    return True


def resolve_medicine_category(scraped, *, existing=None, is_variant_update=False):
    """Return an existing FK or a conservative ATC proposal without mutations.

    Specific task selections bypass this policy entirely. Config subcategories
    retain their previous fallback-only behavior. Never use a variant's ATC to
    classify the base card, and never create missing taxonomy nodes here.
    """
    root = scraped._medicine_category_root
    current = existing.category if existing is not None else None
    medicine = (
        validate_existing_medicine(scraped, existing, is_variant_update=is_variant_update)
        if existing is not None else None
    )
    domain_category = medicine.category if medicine is not None else None
    current_specific = current is not None and current.pk != root.pk
    domain_specific = domain_category is not None and domain_category.pk != root.pk
    if current_specific and domain_specific and current.pk != domain_category.pk:
        raise MedicineCategoryConflict("Product and MedicineProduct categories disagree")
    if current_specific:
        return current
    if domain_specific:
        # Keep an existing domain assignment when an old shadow still has root/null.
        return domain_category

    attrs = scraped.attributes if isinstance(scraped.attributes, dict) else {}
    previous = existing.external_data if existing is not None else {}
    previous = previous if isinstance(previous, dict) else {}
    old_attrs = previous.get("attributes") or {}
    old_attrs = old_attrs if isinstance(old_attrs, dict) else {}
    domain_data = medicine.external_data if medicine is not None else {}
    domain_data = domain_data if isinstance(domain_data, dict) else {}
    domain_attrs = domain_data.get("attributes") or {}
    domain_attrs = domain_attrs if isinstance(domain_attrs, dict) else {}
    # Unknown existing cards stay exactly where they were, including NULL.
    # Assigning the root as a fallback could silently change their markup.
    fallback = current if existing is not None else root
    if not getattr(settings, "MEDICINE_CATEGORY_AUTOMATION_ENABLED", False):
        return fallback
    if not Category.objects.filter(pk=root.pk, is_active=True, parent__isnull=True).exists():
        return fallback
    if any(value is True for value in (
        attrs.get("is_stub"), previous.get("is_stub"), old_attrs.get("is_stub"),
        domain_data.get("is_stub"), domain_attrs.get("is_stub"),
    )):
        return fallback
    if any(data.get(key) for data in (attrs, previous, old_attrs, domain_data, domain_attrs)
           for key in ("source_variant_id", "source_variant_slug")):
        return current

    source_barcode = attrs.get("barcode") or scraped.barcode
    if scraped.barcode and attrs.get("barcode"):
        if str(scraped.barcode).strip() != str(attrs["barcode"]).strip():
            return fallback
    # Never refine from old stored ATC alone when the fresh page is incomplete.
    if not str(attrs.get("atc_code") or "").strip() or not str(source_barcode or "").strip():
        return fallback
    proposal = propose_medicine_category(
        atc_code=(medicine.atc_code if medicine is not None else "") or old_attrs.get("atc_code"),
        source_atc_code=attrs.get("atc_code"),
        barcode=(medicine.barcode if medicine is not None else "") or old_attrs.get("barcode"),
        source_barcode=source_barcode,
    )
    if proposal.status != "proposed":
        return fallback
    return (
        Category.objects.filter(
            slug=proposal.category_slug, parent=root, is_active=True,
        ).first()
        or fallback
    )
