"""Кнопки «Посмотреть на сайте» и «Источник» на странице товара в админке."""
from django import template
from django.utils.html import format_html, format_html_join

from apps.catalog.admin_links import product_view_buttons

register = template.Library()


@register.simple_tag
def product_view_buttons_items(obj):
    """Пункты блока кнопок вверху формы; у не-товара и у новой записи — пусто."""
    if obj is None or not getattr(obj, "pk", None):
        return ""
    return format_html_join(
        "",
        '<li><a href="{}" class="viewsitelink" target="_blank" rel="noopener noreferrer" title="{}">{}</a></li>',
        ((button["url"], button["title"], button["label"]) for button in product_view_buttons(obj)),
    )
