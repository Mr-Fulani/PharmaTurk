from django import template

from apps.drug_check.sources.base import fmt_price

register = template.Library()


@register.filter
def tl(value):
    """202.15 → «202,15 TL»."""
    return fmt_price(value) if value is not None and value != "" else ""
