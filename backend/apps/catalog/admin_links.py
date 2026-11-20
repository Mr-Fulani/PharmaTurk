"""Ссылка «товар в админке»: страница доменной записи (лекарство, БАД, обувь…), иначе общая карточка.

Только на странице доменной записи есть свои панели раздела — например, у лекарства
«Наличие и цена: проверка по источникам» (docs/DRUG_CHECK.md).
"""
from django.db.models import Prefetch
from django.urls import NoReverseMatch, reverse

from .domain_sync import domain_models


def _accessor(model) -> str:
    return model._meta.get_field("base_product").remote_field.get_accessor_name()


def domain_record_prefetches(product_path: str = "") -> list:
    """Предзагрузка доменных записей для product_admin_url: по запросу на тип, а не на строку списка.

    product_path — путь до товара от модели списка («product» для позиции заказа).
    """
    prefix = f"{product_path}__" if product_path else ""
    return [
        Prefetch(f"{prefix}{_accessor(model)}", queryset=model.objects.only("pk", "base_product_id"))
        for model in domain_models().values()
    ]


def product_admin_url(product) -> str:
    """Адрес страницы доменной записи товара (по его текущему типу); если её нет — общей карточки."""
    model = domain_models().get(str(product.product_type or "").replace("-", "_"))
    record = getattr(product, _accessor(model), None) if model else None
    if record is not None:
        try:
            return reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_change", args=[record.pk])
        except NoReverseMatch:  # у типа нет своего раздела в админке
            pass
    return reverse("admin:catalog_product_change", args=[product.pk])


SOURCE_BUTTONS_LIMIT = 5


def _base_product(obj):
    """Общий Product карточки админки: сам товар или базовый товар доменной записи; иначе None."""
    from .models import AbstractDomainProduct, Product

    if isinstance(obj, Product):
        return obj
    if isinstance(obj, AbstractDomainProduct):
        return getattr(obj, "base_product", None)
    return None


def _is_shadow(product) -> bool:
    """Служебная запись без страницы на сайте (как non_public_shadow_product_q)."""
    data = product.external_data or {}
    if "source_variant_id" in data or "source_variant_slug" in data:
        return True
    return product.product_type == "medicines" and data.get("is_stub") is True


def product_site_url(obj) -> str:
    """Адрес карточки на сайте; пусто — товар скрыт (страницы нет)."""
    from .services.product_resolve import build_canonical_path
    from .services.yml_feed import feed_site_url

    product = _base_product(obj)
    # Страницу сайт находит по slug активного Product (product_resolve)
    if product is None or not product.slug or not product.is_active or not obj.is_active or _is_shadow(product):
        return ""
    return f"{feed_site_url()}{build_canonical_path(product.product_type, product.slug)}"


def product_source_urls(obj) -> list[str]:
    """Адреса товара у продавцов без повторов: ссылка товара, затем предложения источников."""
    product = _base_product(obj)
    urls = [getattr(obj, "external_url", "")]
    if product is not None:
        urls.append(product.external_url)
        urls.extend(
            product.source_offers.order_by("canonical_url").values_list("canonical_url", flat=True).distinct()
        )
    return list(dict.fromkeys(url for url in urls if url and url.startswith(("https://", "http://"))))


def product_view_buttons(obj) -> list[dict]:
    """Кнопки карточки товара в админке: «Посмотреть на сайте» и по кнопке на источник."""
    from urllib.parse import urlsplit

    from django.utils.translation import gettext as _

    product = _base_product(obj)
    if product is None:
        return []
    buttons = []
    site_url = product_site_url(obj)
    if site_url:
        buttons.append({"url": site_url, "label": _("Посмотреть на сайте"), "title": site_url})
    sources = product_source_urls(obj)
    seen = {}
    for url in sources[:SOURCE_BUTTONS_LIMIT]:
        domain = (urlsplit(url).hostname or "").removeprefix("www.")
        seen[domain] = seen.get(domain, 0) + 1
        # Несколько ссылок одного продавца (расцветки) различаются номером
        suffix = f" · {seen[domain]}" if seen[domain] > 1 else ""
        buttons.append({"url": url, "label": _("Источник: %(domain)s") % {"domain": domain} + suffix, "title": url})
    rest = len(sources) - SOURCE_BUTTONS_LIMIT
    if rest > 0:
        offers_url = reverse("admin:catalog_productsourceoffer_changelist")
        buttons.append({
            "url": f"{offers_url}?product__id__exact={product.pk}",
            "label": _("Ещё источников: %(count)s") % {"count": rest},
            "title": _("Все предложения источников этого товара"),
        })
    return buttons
