"""Напоминания о неотправленном Списке заявки: отбор, частота, отписка, тексты ru/en, админка."""

import re
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from django.core import signing
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import Product, ProductTranslation
from apps.orders import cart_reminders
from apps.orders.models import (
    Cart,
    CartItem,
    CartReminderLog,
    CartReminderSettings,
    Order,
    SourcingRequest,
)
from apps.users.models import User
from apps.users.telegram_auth import CART_REMINDERS_OFF_CALLBACK, process_telegram_webhook

TG_OK = SimpleNamespace(ok=True, status_code=200, text="")


@pytest.fixture(autouse=True)
def _site(settings, monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *a, **k: None)
    settings.FRONTEND_SITE_URL = "https://mudaroba.com"
    settings.TELEGRAM_BOT_TOKEN = "token"


@pytest.fixture
def conf():
    obj = CartReminderSettings.load()
    obj.enabled = True
    obj.save()
    return obj


def _user(**extra):
    data = dict(
        username=f"cr-{uuid4().hex[:10]}",
        email=f"{uuid4().hex[:8]}@example.test",
        password="x",
        is_verified=True,
    )
    data.update(extra)
    return User.objects.create_user(**data)


def _cart(user, hours_ago=30, name="Магний B6", locale="ru", currency="RUB", **cart_fields):
    product = Product.objects.create(
        name=name,
        slug=f"cr-{uuid4().hex[:10]}",
        product_type="medicines",
        price=Decimal("100"),
        currency="RUB",
        is_available=True,
        stock_quantity=5,
    )
    cart = Cart.objects.create(user=user, currency=currency, locale=locale)
    CartItem.objects.create(cart=cart, product=product, quantity=2, price=Decimal("100"), currency=currency)
    Cart.objects.filter(pk=cart.pk).update(updated_at=timezone.now() - timedelta(hours=hours_ago), **cart_fields)
    cart.refresh_from_db()
    return cart


def _due_ids(conf):
    return set(cart_reminders.due_carts(conf).values_list("pk", flat=True))


def _run():
    with patch("apps.orders.tasks._send_email_with_ipv4_fallback") as send_email, \
            patch("apps.orders.cart_reminders.requests.post", return_value=TG_OK) as tg_post:
        sent = cart_reminders.run_cart_reminders()
    return sent, send_email, tg_post


# ─── Отбор получателей ───────────────────────────────────────────────────────


@pytest.mark.django_db
def test_disabled_by_default_sends_nothing():
    _cart(_user(telegram_id="701", telegram_notifications=True))

    sent, send_email, tg_post = _run()

    assert CartReminderSettings.load().enabled is False
    assert sent == 0
    send_email.assert_not_called()
    tg_post.assert_not_called()
    assert not CartReminderLog.objects.exists()


@pytest.mark.django_db
def test_recipient_selection(conf):
    due = _cart(_user())
    _cart(_user(), hours_ago=5)  # ещё не прошло 24 ч
    _cart(_user(), hours_ago=24 * 8)  # старше max_age_days
    _cart(_user(is_verified=False))  # email не подтверждён, Telegram нет
    _cart(_user(email=f"tg_{uuid4().hex[:6]}@mudaroba.local"))  # технический email
    _cart(_user(cart_reminders_enabled=False))  # отписался
    _cart(_user(is_active=False))
    empty = Cart.objects.create(user=_user())
    Cart.objects.filter(pk=empty.pk).update(updated_at=timezone.now() - timedelta(hours=30))
    guest = Cart.objects.create(session_key=uuid4().hex)
    CartItem.objects.create(cart=guest, product=Product.objects.first(), quantity=1, price=Decimal("1"), currency="RUB")
    Cart.objects.filter(pk=guest.pk).update(updated_at=timezone.now() - timedelta(hours=30))
    tg_only = _cart(_user(is_verified=False, telegram_id="702", telegram_notifications=True))

    assert _due_ids(conf) == {due.pk, tg_only.pk}


@pytest.mark.django_db
def test_request_or_sourcing_after_cart_change_stops_reminders(conf):
    with_order = _cart(_user())
    Order.objects.create(
        user=with_order.user, number=f"CR{uuid4().hex[:8]}", contact_name="К", contact_phone="+79990001122",
    )
    with_sourcing = _cart(_user())
    SourcingRequest.objects.create(user=with_sourcing.user, contact_name="К", contact_phone="+79990001122")
    old_order = _cart(_user())
    order = Order.objects.create(
        user=old_order.user, number=f"CR{uuid4().hex[:8]}", contact_name="К", contact_phone="+79990001122",
    )
    Order.objects.filter(pk=order.pk).update(created_at=old_order.updated_at - timedelta(hours=1))

    # Заявка до изменения Списка не мешает: клиент добавил новые товары и не отправил их
    assert _due_ids(conf) == {old_order.pk}


@pytest.mark.django_db
def test_channels_follow_settings_and_bindings(conf):
    both = _cart(_user(telegram_id="703", telegram_notifications=True))
    email_only = _cart(_user())

    _run()

    assert set(CartReminderLog.objects.filter(cart=both).values_list("channel", flat=True)) == {"email", "telegram"}
    assert list(CartReminderLog.objects.filter(cart=email_only).values_list("channel", flat=True)) == ["email"]


@pytest.mark.django_db
def test_channel_switches_in_settings(conf, settings):
    tg_cart = _cart(_user(is_verified=False, telegram_id="709", telegram_notifications=True))
    email_cart = _cart(_user())

    conf.email_enabled = False
    conf.save()
    assert _due_ids(conf) == {tg_cart.pk}

    conf.email_enabled, conf.telegram_enabled = True, False
    conf.save()
    assert _due_ids(conf) == {email_cart.pk}

    conf.email_enabled, conf.telegram_enabled = False, True
    conf.save()
    settings.TELEGRAM_BOT_TOKEN = ""
    assert _due_ids(conf) == set()


# ─── Частота и защита от дублей ─────────────────────────────────────────────


@pytest.mark.django_db
def test_first_then_second_then_nothing(conf):
    cart = _cart(_user(telegram_id="704", telegram_notifications=True), hours_ago=30)

    sent, send_email, tg_post = _run()
    assert sent == 1
    assert send_email.call_count == 1 and tg_post.call_count == 1
    cart.refresh_from_db()
    assert cart.reminder_count == 1

    sent, send_email, _tg = _run()  # повтор в тот же час
    assert sent == 0
    send_email.assert_not_called()

    Cart.objects.filter(pk=cart.pk).update(
        updated_at=timezone.now() - timedelta(hours=80), reminder_sent_at=timezone.now() - timedelta(hours=50),
    )
    sent, _email, _tg = _run()
    assert sent == 1
    assert set(CartReminderLog.objects.values_list("step", flat=True)) == {1, 2}

    Cart.objects.filter(pk=cart.pk).update(updated_at=timezone.now() - timedelta(hours=120))
    sent, send_email, _tg = _run()
    assert sent == 0
    send_email.assert_not_called()
    assert CartReminderLog.objects.filter(status=CartReminderLog.Status.SENT).count() == 4


@pytest.mark.django_db
def test_new_cycle_waits_for_pause(conf):
    # Клиент получил напоминания 3 дня назад, потом снова изменил Список (30 ч назад)
    cart = _cart(_user(), hours_ago=30, reminder_sent_at=timezone.now() - timedelta(days=3), reminder_count=2)
    assert _due_ids(conf) == set()  # пауза 7 дней после прошлого напоминания

    Cart.objects.filter(pk=cart.pk).update(reminder_sent_at=timezone.now() - timedelta(days=8))
    assert _due_ids(conf) == {cart.pk}
    _run()
    cart.refresh_from_db()
    assert cart.reminder_count == 1


@pytest.mark.django_db
def test_second_reminder_can_be_disabled(conf):
    conf.second_delay_hours = 0
    conf.save()
    _cart(_user(), hours_ago=100, reminder_sent_at=timezone.now() - timedelta(hours=70), reminder_count=1)

    assert _due_ids(conf) == set()


@pytest.mark.django_db
def test_claim_happens_once_for_concurrent_runs(conf):
    cart = _cart(_user())
    stale_copy = Cart.objects.get(pk=cart.pk)
    now = timezone.now()

    assert cart_reminders._claim_step(cart, now) == 1
    assert cart_reminders._claim_step(stale_copy, now) is None


@pytest.mark.django_db
def test_send_error_is_logged_and_batch_continues(conf):
    first = _cart(_user(), hours_ago=40)
    second = _cart(_user(), hours_ago=30)

    with patch("apps.orders.tasks._send_email_with_ipv4_fallback", side_effect=[OSError("smtp down"), None]):
        sent = cart_reminders.run_cart_reminders()

    assert sent == 1
    failed = CartReminderLog.objects.get(cart=first)
    assert failed.status == CartReminderLog.Status.FAILED
    assert "smtp down" in failed.error
    assert CartReminderLog.objects.get(cart=second).status == CartReminderLog.Status.SENT


@pytest.mark.django_db
def test_task_is_noop_while_disabled():
    from apps.orders.tasks import remind_abandoned_carts

    _cart(_user())
    with patch("apps.orders.tasks._send_email_with_ipv4_fallback") as send_email:
        assert remind_abandoned_carts.run() == 0
    send_email.assert_not_called()


# ─── Содержимое ru/en ───────────────────────────────────────────────────────


def _render(cart, step=1):
    log = CartReminderLog.objects.create(user=cart.user, cart=cart, step=step, channel="email")
    with patch("apps.orders.serializers.CartItemSerializer.get_price", return_value=Decimal("1500")):
        content = cart_reminders.build_reminder_content(
            cart.user, cart_reminders._cart_items(cart), cart.currency, cart.locale,
        )
    return content, log


def _link_targets(text):
    targets = []
    for url in re.findall(r"https://mudaroba\.com/api/orders/cart-reminders/go/\?t=[^\s\"<]+", text):
        token = parse_qs(urlsplit(url.replace("&amp;", "&")).query)["t"][0]
        targets.append(cart_reminders.resolve_click_token(token)[1])
    return targets


def _visible_text(html_body, text):
    """Что читает клиент: без тегов с атрибутами (href, src) и без адресов — в токенах ссылок
    случайные буквы, «buy» в них встречается."""
    visible = re.sub(r"<[^>]+>", " ", html_body) + " " + text
    return re.sub(r"https?://\S+", " ", visible).lower()


def test_visible_text_ignores_link_tokens():
    # Случай из CI: подписанный токен «…amguweeojxzbuyijko…» в ссылке
    link = "https://mudaroba.com/api/orders/cart-reminders/go/?t=amguweeojxzbuyijko"
    visible = _visible_text(f'<a href="{link}"><img src="{link}" alt="Send request"></a> Send request', link)

    assert "buy" not in visible
    assert "send request" in visible


@pytest.mark.django_db
def test_email_ru_lists_items_with_current_price_and_neutral_wording():
    cart = _cart(_user())
    product = cart.items.get().product
    product.main_image = "https://cdn.mudaroba.com/products/magnesium.jpg"
    product.save(update_fields=["main_image"])
    ProductTranslation.objects.create(product=product, locale="ru", name="Магний B6, 50 таблеток")

    content, log = _render(cart)
    subject, text, html_body = cart_reminders.render_email(cart.user, content, log)

    assert subject == "Ваш Список заявки ждёт"
    assert "Магний B6, 50 таблеток" in html_body and "Магний B6, 50 таблеток" in text
    assert "1 500 ₽" in html_body  # цена за штуку
    assert "3 000 ₽" in html_body  # 2 × 1500
    assert "https://cdn.mudaroba.com/products/magnesium.jpg" in html_body  # без proxy-image
    assert "Отправить заявку" in html_body and "Открыть Список заявки" in html_body
    assert "/api/orders/cart-reminders/unsubscribe/?t=" in html_body
    visible = _visible_text(html_body, text)
    assert "магний b6, 50 таблеток" in visible
    for wording in ("купить", "купите", "покупк"):
        assert wording not in visible
    targets = _link_targets(html_body)
    assert any(t.startswith(f"/product/{product.slug}?utm_source=cart_reminder&utm_medium=email") for t in targets)
    assert any(t.startswith("/checkout?") and "utm_campaign=cart_reminder_1" in t for t in targets)
    assert any(t.startswith("/cart?") and "utm_content=cart" in t for t in targets)


@pytest.mark.django_db
def test_email_en_uses_english_texts_and_en_links():
    cart = _cart(_user(), locale="en", currency="USD")
    product = cart.items.get().product
    ProductTranslation.objects.create(product=product, locale="en", name="Magnesium B6, 50 tablets")

    content, log = _render(cart, step=2)
    subject, text, html_body = cart_reminders.render_email(cart.user, content, log)

    assert subject == "Items in your request list are still waiting for you"
    assert "Magnesium B6, 50 tablets" in html_body
    assert "1,500.00 $" in html_body
    assert "Send request" in html_body
    visible = _visible_text(html_body, text)
    assert "send request" in visible
    assert not re.search(r"\bbuy", visible)
    targets = _link_targets(html_body)
    assert any(t.startswith(f"/en/product/{product.slug}?") for t in targets)
    assert any(t.startswith("/en/checkout?") and "utm_campaign=cart_reminder_2" in t for t in targets)


@pytest.mark.django_db
def test_telegram_message_escapes_names_and_has_stop_button():
    cart = _cart(_user(telegram_id="705", telegram_notifications=True), name="Крем <Aloe & Co>")
    content, log = _render(cart)
    log.channel = "telegram"

    text, markup = cart_reminders.render_telegram(content, log)

    assert "Крем &lt;Aloe &amp; Co&gt;" in text
    assert "<b>Ваш Список заявки ждёт</b>" in text
    buttons = [button for row in markup["inline_keyboard"] for button in row]
    assert buttons[0]["text"] == "Отправить заявку"
    assert buttons[-1]["callback_data"] == CART_REMINDERS_OFF_CALLBACK
    targets = _link_targets(text) + _link_targets(" ".join(b.get("url", "") for b in buttons))
    assert targets and all("utm_medium=telegram" in t for t in targets)


@pytest.mark.django_db
def test_telegram_message_fits_limit_with_long_names():
    cart = _cart(_user(telegram_id="710", telegram_notifications=True))
    content, log = _render(cart)
    content["items"] = [{**content["items"][0], "name": "Очень длинное название " * 30} for _ in range(15)]

    text, _markup = cart_reminders.render_telegram(content, log)

    visible = re.sub(r"<[^>]+>", "", text)
    assert len(visible) < 4096
    assert "и ещё 5" in visible


def test_resend_payload_carries_unsubscribe_headers(settings):
    from django.core.mail import EmailMultiAlternatives

    from apps.orders.tasks import _send_email_via_resend

    settings.RESEND_API_KEY = "key"
    message = EmailMultiAlternatives(
        subject="S", body="B", to=["client@example.test"],
        headers={"List-Unsubscribe": "<https://mudaroba.com/x>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"},
    )
    with patch("apps.orders.tasks.requests.post", return_value=SimpleNamespace(status_code=200, text="")) as post:
        assert _send_email_via_resend(message) is True

    assert post.call_args.kwargs["json"]["headers"]["List-Unsubscribe"] == "<https://mudaroba.com/x>"


def test_format_money_matches_site():
    assert cart_reminders.format_money(Decimal("1234.5"), "RUB", "ru") == "1 235 ₽"
    assert cart_reminders.format_money(Decimal("1234.5"), "USD", "en") == "1,234.50 $"
    assert cart_reminders.format_money(Decimal("10"), "EUR", "ru") == "10,00 €"


# ─── Отписка и переходы ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_unsubscribe_page_asks_then_disables():
    user = _user()
    url = cart_reminders.unsubscribe_url(user, "ru").replace("https://mudaroba.com", "")

    page = Client().get(url)
    assert page.status_code == 200
    assert "Не присылать напоминания" in page.content.decode()
    assert page["Cache-Control"] == "private, no-store"
    user.refresh_from_db()
    assert user.cart_reminders_enabled is True  # GET (сканер ссылок) ничего не меняет

    done = Client().post(url)
    assert done.status_code == 200
    assert "напоминания отключены" in done.content.decode()
    user.refresh_from_db()
    assert user.cart_reminders_enabled is False


@pytest.mark.django_db
def test_one_click_unsubscribe_and_bad_token():
    user = _user()
    url = cart_reminders.unsubscribe_url(user, "en").replace("https://mudaroba.com", "")

    response = Client().post(url, data="List-Unsubscribe=One-Click", content_type="application/x-www-form-urlencoded")
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.cart_reminders_enabled is False

    bad = Client().post(reverse("cart-reminder-unsubscribe") + "?t=forged")
    assert bad.status_code == 400


@pytest.mark.django_db
def test_click_redirects_inside_site_and_marks_log():
    cart = _cart(_user())
    log = CartReminderLog.objects.create(user=cart.user, cart=cart, step=1, channel="email")
    link = cart_reminders._tracked_link(log, "/cart", "cart", "ru").replace("https://mudaroba.com", "")

    response = Client().get(link)

    assert response.status_code == 302
    assert response["Location"].startswith("https://mudaroba.com/cart?utm_source=cart_reminder")
    log.refresh_from_db()
    assert log.clicked_at is not None

    evil = signing.dumps([log.pk, "//evil.example/x"], salt=cart_reminders.CLICK_SALT, compress=True)
    response = Client().get(reverse("cart-reminder-click"), {"t": evil})
    assert response["Location"] == "https://mudaroba.com/"
    response = Client().get(reverse("cart-reminder-click"), {"t": "forged"})
    assert response["Location"] == "https://mudaroba.com/"


@pytest.mark.django_db
def test_telegram_stop_button_and_command_disable_reminders():
    user = _user(telegram_id="706", telegram_notifications=True)
    other = _user(telegram_id="707", telegram_notifications=True)
    callback = {
        "update_id": 1,
        "callback_query": {
            "id": "cb1",
            "from": {"id": 706, "language_code": "ru"},
            "message": {"chat": {"id": 706, "type": "private"}},
            "data": CART_REMINDERS_OFF_CALLBACK,
        },
    }
    with patch("apps.users.telegram_auth._send_telegram_message") as reply, \
            patch("apps.users.telegram_auth._answer_callback_query") as answer:
        assert process_telegram_webhook(callback) is True
        answer.assert_called_once_with("cb1")
        assert "отключены" in reply.call_args.args[1]

        stop = {"message": {"text": "/stop", "from": {"id": 707}, "chat": {"id": 707, "type": "private"}}}
        assert process_telegram_webhook(stop) is True

    user.refresh_from_db()
    other.refresh_from_db()
    assert user.cart_reminders_enabled is False
    assert other.cart_reminders_enabled is False


@pytest.mark.django_db
def test_telegram_callback_from_foreign_chat_is_ignored():
    user = _user(telegram_id="708", telegram_notifications=True)
    callback = {
        "callback_query": {
            "id": "cb2",
            "from": {"id": 708},
            "message": {"chat": {"id": -100500, "type": "group"}},
            "data": CART_REMINDERS_OFF_CALLBACK,
        },
    }
    with patch("apps.users.telegram_auth._send_telegram_message"), \
            patch("apps.users.telegram_auth._answer_callback_query"):
        assert process_telegram_webhook(callback) is False
    user.refresh_from_db()
    assert user.cart_reminders_enabled is True


@pytest.mark.django_db
def test_profile_api_exposes_reminders_switch():
    user = _user()
    client = APIClient()
    client.force_authenticate(user)

    response = client.patch(f"/api/users/profile/{user.pk}", {"cart_reminders_enabled": False}, format="json")

    assert response.status_code == 200, response.content
    user.refresh_from_db()
    assert user.cart_reminders_enabled is False


@pytest.mark.django_db
def test_cart_add_remembers_page_locale():
    user = _user()
    product = Product.objects.create(
        name="Locale product", slug=f"cr-loc-{uuid4().hex[:8]}", product_type="medicines",
        price=Decimal("10"), currency="RUB", is_available=True, stock_quantity=5,
    )
    client = APIClient()
    client.force_authenticate(user)

    response = client.post(
        reverse("cart-add"), {"product_id": product.pk, "quantity": 1}, format="json", HTTP_ACCEPT_LANGUAGE="en",
    )

    assert response.status_code == 200, response.content
    assert Cart.objects.get(user=user).locale == "en"


# ─── Админка ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_admin_test_send_goes_to_current_admin(settings):
    settings.STORAGES = {**settings.STORAGES, "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    }}
    admin_user = _user(is_staff=True, is_superuser=True, is_verified=False)
    Product.objects.create(
        name="Sample", slug=f"cr-s-{uuid4().hex[:8]}", product_type="medicines",
        price=Decimal("10"), currency="RUB", is_available=True,
    )
    client = Client()
    client.force_login(admin_user)

    page = client.get(reverse("admin:orders_cartremindersettings_changelist"), follow=True)
    assert page.status_code == 200
    assert "Отправить тестовое мне" in page.content.decode()

    with patch("apps.orders.tasks._send_email_with_ipv4_fallback") as send_email:
        response = client.post(reverse("admin:orders_cartremindersettings_send_test"), {"locale": "en"})

    assert response.status_code == 302
    message = send_email.call_args.args[0]
    assert message.to == [admin_user.email]
    assert message.subject == "Test: your request list is waiting"
    assert message.extra_headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    log = CartReminderLog.objects.get()
    assert log.step == CartReminderLog.Step.TEST and log.status == CartReminderLog.Status.SENT

    journal = client.get(reverse("admin:orders_cartreminderlog_changelist"))
    assert journal.status_code == 200


@pytest.mark.django_db
def test_test_send_respects_channel_checkboxes(settings):
    """Тест «себе» идёт только в каналы с галочкой (владелец, 27.10.2026: письмо уходило при снятой)."""
    from apps.orders.cart_reminders import send_test_reminder

    settings.TELEGRAM_BOT_TOKEN = "t"
    conf = CartReminderSettings.load()
    conf.email_enabled = False
    conf.save()
    admin_user = _user(is_staff=True, telegram_id="711", telegram_notifications=True)
    _cart(admin_user)

    with patch("apps.orders.tasks._send_email_with_ipv4_fallback") as send_email, \
            patch("apps.orders.cart_reminders.requests.post", return_value=TG_OK) as tg_post:
        logs = send_test_reminder(admin_user)

    send_email.assert_not_called()
    tg_post.assert_called_once()
    assert [log.channel for log in logs] == [CartReminderLog.Channel.TELEGRAM]

    conf.telegram_enabled = False
    conf.save()
    assert send_test_reminder(admin_user) == []


@pytest.mark.django_db
def test_telegram_chat_not_found_explains_start(settings):
    from apps.orders.cart_reminders import send_test_reminder

    settings.TELEGRAM_BOT_TOKEN = "t"
    settings.TELEGRAM_BOT_USERNAME = "mudaroba_bot"
    conf = CartReminderSettings.load()
    conf.email_enabled = False
    conf.save()
    admin_user = _user(is_staff=True, telegram_id="712", telegram_notifications=True)
    _cart(admin_user)
    not_found = SimpleNamespace(
        ok=False, status_code=400, text='{"ok":false,"error_code":400,"description":"Bad Request: chat not found"}'
    )

    with patch("apps.orders.cart_reminders.requests.post", return_value=not_found):
        (log,) = send_test_reminder(admin_user)

    assert log.status == CartReminderLog.Status.FAILED
    assert "откройте @mudaroba_bot в Telegram и нажмите Start" in log.error
    assert "chat not found" in log.error


@pytest.mark.django_db
def test_admin_action_marks_client_contacted(conf, rf):
    from django.contrib.admin.sites import AdminSite
    from django.contrib.messages.storage.fallback import FallbackStorage

    from apps.orders.admin import CartAdmin

    cart = _cart(_user())
    request = rf.post("/admin/")
    request.user = _user(is_staff=True, is_superuser=True)
    request.session = {}
    request._messages = FallbackStorage(request)

    CartAdmin(Cart, AdminSite()).stop_cart_reminders(request, Cart.objects.filter(pk=cart.pk))

    assert _due_ids(conf) == set()
