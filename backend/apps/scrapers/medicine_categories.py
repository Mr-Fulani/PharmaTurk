"""Opt-in medicine category refinement. No saves, seeding or source requests."""

from django.conf import settings

from apps.catalog.medicine_taxonomy import propose_medicine_category
from apps.catalog.models import Category, MedicineProduct


class MedicineCategoryConflict(Exception):
    """Two existing specific category assignments require human reconciliation."""


def prepare_medicine_category_mapping(session, scraped):
    """A task root outranks config defaults, but is not a forced leaf override."""
    scraped.__dict__.pop("_medicine_category_root", None)
    if not getattr(settings, "MEDICINE_CATEGORY_AUTOMATION_ENABLED", False):
        return False
    if str(scraped.source or "").strip().lower() != "ilacfiyati":
        return False
    category = session.target_category or session.scraper_config.default_category
    if not category or category.slug != "medicines" or category.parent_id is not None:
        return False
    if not category.is_active:
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
    if existing is not None and (is_variant_update or existing.product_type != "medicines"):
        return current

    medicine = (
        MedicineProduct.objects.filter(base_product_id=existing.pk)
        .select_related("category").first()
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
    fallback = current or root
    if any(value is True for value in (
        attrs.get("is_stub"), previous.get("is_stub"), old_attrs.get("is_stub"),
        domain_data.get("is_stub"), domain_attrs.get("is_stub"),
    )):
        return fallback
    if previous.get("source_variant_id") or previous.get("source_variant_slug"):
        return current

    source_barcode = attrs.get("barcode") or scraped.barcode
    if scraped.barcode and attrs.get("barcode"):
        if str(scraped.barcode).strip() != str(attrs["barcode"]).strip():
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
