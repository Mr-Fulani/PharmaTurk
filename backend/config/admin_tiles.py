"""Плитки часто нужных разделов на главной странице админки (docs/ADMIN_HOME_TILES.md)."""

import logging
from datetime import timedelta

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)


def _count(queryset):
    """Число строк; при ошибке — None: плитка останется без числа, главная не упадёт."""
    try:
        with transaction.atomic():  # ошибка запроса не должна испортить транзакцию страницы
            return queryset.count()
    except Exception:
        logger.warning("admin_home_tile_count_failed", exc_info=True)
        return None


def _since(**delta):
    return timezone.now() - timedelta(**delta)


def _orders(url):
    from apps.orders.admin import OPEN_PROCESSING
    from apps.orders.models import Order

    return {
        "icon": "🧾", "title": "Заявки", "url": f"{url}?processing=open",
        "value": _count(Order.objects.filter(processing_status__in=OPEN_PROCESSING)), "value_label": "не закрыто",
        "extra": _count(Order.objects.filter(created_at__gte=_since(days=1))), "extra_label": "новых за сутки",
    }


def _sourcing(url):
    from apps.orders.models import SourcingRequest

    return {
        "icon": "🔎", "title": "Найдём товар", "url": f"{url}?status__exact=new",
        "value": _count(SourcingRequest.objects.filter(status=SourcingRequest.Status.NEW)), "value_label": "новых",
    }


def _users(url):
    from apps.users.models import User

    return {
        "icon": "👤", "title": "Пользователи", "url": f"{url}?o=-{_column(User, 'date_joined')}",
        "value": _count(User.objects.all()), "value_label": "всего",
        "extra": _count(User.objects.filter(date_joined__gte=_since(days=7))), "extra_label": "новых за 7 дней",
    }


def _carts(url):
    from apps.orders.models import Cart

    def active(**delta):
        # Список заявки с товарами, который меняли за это время
        return _count(Cart.objects.filter(updated_at__gte=_since(**delta), items__isnull=False).distinct())

    return {
        "icon": "🛒", "title": "Списки заявки (корзины)", "url": f"{url}?o=-{_column(Cart, 'updated_at')}",
        "value": active(days=1), "value_label": "меняли за сутки",
        "extra": active(days=7), "extra_label": "за 7 дней",
    }


def _stock_check(url):
    from apps.catalog.models_stock import StockCheckSourceState

    return {
        "icon": "🌙", "title": "Ночная сверка наличия", "url": url,
        "value": _count(StockCheckSourceState.objects.filter(paused_at__isnull=False)),
        "value_label": "источников на паузе",
    }


def _stale(url):
    from apps.catalog.models_stock import StaleProductCandidate

    status = StaleProductCandidate.Status.CANDIDATE
    return {
        "icon": "🗑️", "title": "Неактуальные товары", "url": f"{url}?status__exact={status}",
        "value": _count(StaleProductCandidate.objects.filter(status=status)), "value_label": "ждут решения",
    }


def _link(icon, title, note=""):
    return lambda url: {"icon": icon, "title": title, "url": url, "note": note}


def _drug_check(url):
    # Поиск и по препаратам, которых нет на сайте (TD-044, docs/DRUG_CHECK.md)
    return {
        "icon": "✅", "title": "Проверка лекарства", "note": "по названию или штрихкоду",
        "url": reverse("admin:drug_check_lookup"),
    }


# (приложение, модель — по ней проверяется право просмотра, сборщик плитки) — в порядке показа
TILES = (
    ("orders", "order", _orders),
    ("orders", "sourcingrequest", _sourcing),
    ("users", "user", _users),
    ("orders", "cart", _carts),
    ("catalog", "productprice", _link("💰", "Цены товаров", "цена каждого товара")),
    ("catalog", "globalcurrencysettings", _link("⚙️", "Настройки цен и наценок", "курсы, наценка")),
    ("catalog", "medicineproduct", _drug_check),
    ("catalog", "medicineproduct", _link("💊", "Лекарства", "каталог")),
    ("catalog", "supplementproduct", _link("🌿", "БАДы", "каталог")),
    ("catalog", "stockchecksourcestate", _stock_check),
    ("catalog", "staleproductcandidate", _stale),
)


def _column(model, field_name) -> int:
    """Номер колонки списка для сортировки (?o=-N)."""
    from django.contrib import admin

    return list(admin.site._registry[model].list_display).index(field_name) + 1


def home_tiles(site, request) -> list[dict]:
    """Плитки главной: только разделы, которые пользователю разрешено смотреть."""
    admins = {(m._meta.app_label, m._meta.model_name): a for m, a in site._registry.items()}
    tiles = []
    for app_label, model_name, build in TILES:
        model_admin = admins.get((app_label, model_name))
        if model_admin is None or not model_admin.has_view_permission(request):
            continue
        try:
            tiles.append(build(reverse(f"{site.name}:{app_label}_{model_name}_changelist")))
        except Exception:
            logger.warning("admin_home_tile_failed", exc_info=True)
    return tiles
