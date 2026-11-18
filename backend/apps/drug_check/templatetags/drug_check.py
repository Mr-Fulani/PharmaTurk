from django import template

from apps.drug_check.sources.base import fmt_price

register = template.Library()


@register.filter
def tl(value):
    """202.15 → «202,15 TL»."""
    return fmt_price(value) if value is not None and value != "" else ""


@register.inclusion_tag("admin/drug_check/_panel.html", takes_context=True)
def drug_check_panel(context, medicine):
    """Панель над полями карточки лекарства: кнопка проверки и итог по своим спискам (без сети)."""
    from django.urls import reverse

    from apps.drug_check.service import quick_check
    from apps.drug_check.sources import file_sources

    report = quick_check(medicine)
    return {
        "medicine": medicine,
        "report": report,
        "check_url": reverse("admin:drug_check_medicine", args=[medicine.pk]),
        "lookup_url": reverse("admin:drug_check_lookup"),
        "loads": [(source.title, source.last_loaded()) for source in file_sources()],
    }
