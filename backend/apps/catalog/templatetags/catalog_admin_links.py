"""Кнопки «На сайте» и «У продавца» на странице товара в админке."""
from django import template
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext as _

from apps.catalog.admin_links import admin_button, product_view_buttons

register = template.Library()

ICONS = {"site": "🌐", "source": "🏪", "more": "📋"}


def _button(button):
    return admin_button(button["url"], button["label"], ICONS[button["kind"]], button["title"])


@register.simple_tag
def product_view_buttons_items(obj):
    """Пункты полосы кнопок вверху формы; у не-товара и у новой записи — пусто.

    Один продавец — кнопка; несколько — одна кнопка с раскрывающимся списком (<details>).
    """
    if obj is None or not getattr(obj, "pk", None):
        return ""
    buttons = product_view_buttons(obj)
    site = [b for b in buttons if b["kind"] == "site"]
    sources = [b for b in buttons if b["kind"] != "site"]
    if len(sources) < 2:
        return format_html_join("", "<li>{}</li>", ((_button(b),) for b in buttons))
    return format_html(
        '{}<li><details class="mud-btn-more"><summary class="mud-btn"><span aria-hidden="true">🏪</span> '
        '{} </summary><div class="mud-btn-more__list">{}</div></details></li>',
        format_html_join("", "<li>{}</li>", ((_button(b),) for b in site)),
        _("У продавца: несколько ссылок"),
        format_html_join("", "{}", ((_button(b),) for b in sources)),
    )
