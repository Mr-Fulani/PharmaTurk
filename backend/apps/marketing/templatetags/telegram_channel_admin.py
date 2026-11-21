"""Кнопка «Пост в Telegram-канал» на странице товара в админке."""

from django import template
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext as _

from apps.catalog.admin_links import _base_product, admin_button
from apps.marketing.telegram_channel import DOMAIN_ACCESSORS

register = template.Library()


@register.simple_tag
def telegram_channel_button_item(obj):
    """Пункт полосы кнопок: предпросмотр поста с «В очередь» и «Опубликовать сейчас»; не товар канала — пусто."""
    if obj is None or not getattr(obj, "pk", None):
        return ""
    product = _base_product(obj)
    if product is None or str(product.product_type or "").replace("-", "_") not in DOMAIN_ACCESSORS:
        return ""
    url = reverse("admin:marketing_telegramchannelpost_product", args=[product.pk])
    return format_html(
        "<li>{}</li>",
        admin_button(
            url, _("Пост в Telegram-канал"), "📣", _("Предпросмотр поста, очередь и публикация")
        ),
    )
