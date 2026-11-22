"""Плитки часто нужных разделов на главной странице админки (docs/ADMIN_HOME_TILES.md)."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission
from django.db import DatabaseError
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Product
from apps.catalog.models_stock import StaleProductCandidate
from apps.orders.models import Cart, CartItem, Order
from config import admin_tiles


@pytest.fixture(autouse=True)
def plain_static(settings):
    # В CI DEBUG=0 и манифестное хранилище статики: без collectstatic шаблон админки падает.
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


def _login(client, django_user_model, *codenames, superuser=False):
    user = django_user_model.objects.create_user(
        username="tiles-admin", email="tiles@example.test", password="x" * 20, is_staff=True, is_superuser=superuser
    )
    user.user_permissions.set(Permission.objects.filter(codename__in=codenames))
    client.force_login(user)
    return user


def _order(number, **extra):
    return Order.objects.create(
        number=number, total_amount=Decimal("100"), currency="RUB", contact_name="Клиент",
        contact_phone="+79990001122", payment_method="manager", **extra,
    )


def _tiles(client):
    response = client.get(reverse("admin:index"))
    assert response.status_code == 200
    return {tile["title"]: tile for tile in response.context["home_tiles"]}, response.content.decode()


@pytest.mark.django_db
def test_tiles_count_and_link(client, django_user_model):
    _login(client, django_user_model, superuser=True)
    old = _order("HT000001")
    Order.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=3))
    _order("HT000002")
    _order("HT000003", processing_status=Order.ProcessingStatus.DONE)
    # «Найдём товар» ведётся в «Заказах»: открытая заявка этого типа и закрытая (в плитку не идёт)
    _order("HT000004", kind=Order.Kind.SOURCING)
    _order("HT000005", kind=Order.Kind.SOURCING, processing_status=Order.ProcessingStatus.CANCELLED)
    product = Product.objects.create(name="Товар", slug="ht-tovar", product_type="accessories")
    StaleProductCandidate.objects.create(
        product=product, parser_key="lcw", source_url="https://lcw.test/1",
        first_seen_at=timezone.now(), last_gone_at=timezone.now(),
    )
    fresh, stale, empty = (Cart.objects.create(session_key=key) for key in "abc")
    for cart in (fresh, stale):
        CartItem.objects.create(cart=cart, product=product, quantity=1, price=Decimal("1"), currency="RUB")
    Cart.objects.filter(pk=stale.pk).update(updated_at=timezone.now() - timedelta(days=3))
    Cart.objects.filter(pk=empty.pk).update(updated_at=timezone.now())

    tiles, html = _tiles(client)

    assert list(tiles) == [
        "Заявки", "Найдём товар", "Пользователи", "Списки заявки (корзины)", "Цены товаров",
        "Настройки цен и наценок", "Проверка лекарства", "Лекарства", "БАДы", "Ночная сверка наличия",
        "Неактуальные товары",
    ]
    assert (tiles["Заявки"]["value"], tiles["Заявки"]["extra"]) == (3, 4)  # не закрытые; новые за сутки
    assert tiles["Заявки"]["url"] == reverse("admin:orders_order_changelist") + "?processing=open"
    assert tiles["Найдём товар"]["value"] == 1
    # По клику — все заявки этого типа, и закрытые тоже: при счётчике 0 список не пустой
    assert tiles["Найдём товар"]["url"] == reverse("admin:orders_order_changelist") + "?kind__exact=sourcing"
    listing = client.get(tiles["Найдём товар"]["url"])
    assert sorted(order.number for order in listing.context["cl"].result_list) == ["HT000004", "HT000005"]
    assert (tiles["Пользователи"]["value"], tiles["Пользователи"]["extra"]) == (1, 1)
    assert (tiles["Списки заявки (корзины)"]["value"], tiles["Списки заявки (корзины)"]["extra"]) == (1, 2)
    assert tiles["Неактуальные товары"]["value"] == 1
    assert tiles["Ночная сверка наличия"]["value"] == 0
    assert tiles["Проверка лекарства"]["url"] == reverse("admin:drug_check_lookup")
    # Плитки — над полем проверки лекарства и полным списком разделов, который остаётся
    assert html.index('id="home-tiles"') < html.index('id="drug-check-search"') < html.index('id="content-main"')
    assert '<span class="mud-tile__value">3</span>' in html and ".mud-tiles" in html
    # Ссылки плиток открываются; списки пользователей и корзин — с сортировкой по дате
    for tile in tiles.values():
        assert client.get(tile["url"]).status_code == 200, tile["url"]
    assert tiles["Пользователи"]["url"].endswith("?o=-7") and tiles["Списки заявки (корзины)"]["url"].endswith("?o=-10")


@pytest.mark.django_db
def test_tiles_few_queries(client, django_user_model, django_assert_max_num_queries):
    _login(client, django_user_model, superuser=True)
    request = client.get(reverse("admin:index")).wsgi_request

    with django_assert_max_num_queries(9 * 3):  # по запросу на счётчик (+ точка сохранения), без запросов на строку
        from django.contrib import admin

        assert len(admin_tiles.home_tiles(admin.site, request)) == 11


@pytest.mark.django_db
def test_tiles_only_for_allowed_sections(client, django_user_model):
    _login(client, django_user_model, "view_order")

    tiles, html = _tiles(client)

    assert list(tiles) == ["Заявки", "Найдём товар"]  # обе плитки ведут в «Заказы»

    django_user_model.objects.filter(username="tiles-admin").delete()
    _login(client, django_user_model)
    tiles, html = _tiles(client)
    assert tiles == {} and 'id="home-tiles"' not in html


@pytest.mark.django_db
def test_broken_counter_leaves_tile_without_number(client, django_user_model):
    _login(client, django_user_model, superuser=True)
    real_count = admin_tiles._count

    def broken(queryset):
        if queryset.model is Order:
            with patch.object(type(queryset), "count", side_effect=DatabaseError("нет таблицы")):
                return real_count(queryset)
        return real_count(queryset)

    with patch.object(admin_tiles, "_count", broken):
        tiles, html = _tiles(client)

    assert tiles["Заявки"]["value"] is None and tiles["Заявки"]["extra"] is None
    assert tiles["Пользователи"]["value"] == 1
    assert "</span> Заявки</span>" in html  # плитка на месте, без числа


@pytest.mark.django_db
def test_broken_tile_is_skipped(client, django_user_model):
    _login(client, django_user_model, superuser=True)
    broken = [("orders", "order", lambda url: 1 / 0), *admin_tiles.TILES[1:]]

    with patch.object(admin_tiles, "TILES", broken):
        tiles, _html = _tiles(client)

    assert "Заявки" not in tiles and "Пользователи" in tiles
