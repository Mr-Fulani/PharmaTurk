"""Telegram-канал: кто попадает в очередь, текст поста, публикация с заглушкой Bot API, расписание, админка."""

import hashlib
import io
import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import IncenseProduct, MedicineProduct, Product, SupplementProduct
from apps.marketing import telegram_channel
from apps.marketing.models import TelegramChannelPost, TelegramChannelSettings
from apps.orders.tasks import TelegramTemporaryError
from apps.users.models import User

Status = TelegramChannelPost.Status


@pytest.fixture(autouse=True)
def _site(settings, monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *a, **k: None)
    settings.FRONTEND_SITE_URL = "https://mudaroba.com"
    settings.TELEGRAM_BOT_TOKEN = "token"
    # Страницы админки в тестах — без манифеста собранной статики
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture
def conf():
    obj = TelegramChannelSettings.load()
    obj.channel_id = "@mudaroba_test"
    obj.enabled = True
    obj.publish_times = "10:00, 19:00"
    obj.save()
    return obj


def _fields(name, **extra):
    data = dict(
        name=name,
        slug=f"tg-{uuid4().hex[:10]}",
        description="<p>Описание товара для поста. Второе предложение.</p>",
        price=Decimal("100"),
        currency="RUB",
        is_available=True,
    )
    data.update(extra)
    return data


def _base(item):
    """Товар в «Товарах»: связь с ним появляется после сохранения записи раздела."""
    item.refresh_from_db()
    assert item.base_product_id
    return item.base_product


def _supplement(**extra):
    item = SupplementProduct.objects.create(
        **_fields(
            "INOVIT Витамин D3 400 МЕ, спрей, 20 мл",
            active_ingredient="Витамин D3 400 МЕ",
            description="<p>Добавка с витамином D3.</p><p>Биологически активная добавка, не является лекарственным средством.</p>",
            **extra,
        )
    )
    return _base(item)


def _medicine(rx=False, **extra):
    item = MedicineProduct.objects.create(
        **_fields(
            "TAVEGYL (клемастин) 1 мг, таблетки, 20 шт.",
            active_ingredient="Клемастин",
            dosage_form="tablet",
            volume="20 таблеток",
            manufacturer="Haleon",
            prescription_required=rx,
            **extra,
        )
    )
    return _base(item)


def _tg_response(ok=True, status=200, description=""):
    payload = (
        {
            "ok": True,
            "result": {"message_id": 77, "chat": {"id": -1001234, "username": "mudaroba_test"}},
        }
        if ok
        else {"ok": False, "description": description}
    )
    return SimpleNamespace(ok=ok, status_code=status, json=lambda: payload)


@pytest.fixture
def telegram():
    """Заглушка Bot API и фото: в настоящий Telegram тесты не ходят."""
    with (
        patch("apps.orders.tasks._post_telegram", return_value=_tg_response()) as post,
        patch.object(telegram_channel, "load_photo", return_value=b"jpeg"),
    ):
        yield post


# ─── Кто попадает в очередь ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_supplement_goes_to_queue_once():
    product = _supplement()
    post, message = telegram_channel.enqueue(product)
    assert post.status == Status.QUEUED and message == "Поставлен в очередь."
    again, message = telegram_channel.enqueue(product)
    assert again.pk == post.pk and message == "Уже в очереди."
    assert TelegramChannelPost.objects.count() == 1


@pytest.mark.django_db
def test_import_restricted_medicine_goes_to_queue():
    """Решение владельца 21.11.2026: лекарства с меткой «Ввоз ограничен» в канал идут."""
    product = _medicine()
    MedicineProduct.objects.filter(base_product=product).update(import_restricted_countries="KZ,RU")
    post, message = telegram_channel.enqueue(Product.objects.get(pk=product.pk))
    assert post.status == Status.QUEUED and message == "Поставлен в очередь."


@pytest.mark.django_db
def test_hidden_product_is_not_queued():
    product = _supplement()
    Product.objects.filter(pk=product.pk).update(is_active=False)
    post, message = telegram_channel.enqueue(Product.objects.get(pk=product.pk))
    assert post is None and "скрыт" in message

    product = _supplement()
    SupplementProduct.objects.filter(base_product=product).update(is_active=False)
    assert telegram_channel.enqueue(Product.objects.get(pk=product.pk))[0] is None


@pytest.mark.django_db
def test_other_product_types_are_not_queued():
    product = Product.objects.create(
        name="Кроссовки", slug=f"tg-{uuid4().hex[:8]}", product_type="shoes"
    )
    post, message = telegram_channel.enqueue(product)
    assert post is None and "только лекарства" in message


# ─── Текст поста ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_supplement_post_text():
    content = telegram_channel.build_post(_supplement(), today=datetime(2026, 11, 21).date())
    text = content["text"]
    assert "<b>INOVIT Витамин D3 400 МЕ, спрей, 20 мл</b>" in text
    assert "▫️ Состав: Витамин D3 400 МЕ" in text
    assert "Доставка из Турции: 3–14 дней" in text
    assert "Добавка с витамином D3." in text
    assert "💰 Цена: <b>" in text and "₽</b> (на 21.11.2026)" in text
    assert "<i>БАД. Не является лекарством.</i>" in text
    assert "лекарственным средством" not in text  # оговорка из описания не дублируется
    assert "#БАДы" in text
    assert content["button_text"] == "Открыть на сайте"
    assert content["url"].startswith("https://mudaroba.com/product/")
    assert content["url"].endswith("?utm_source=telegram&utm_medium=channel")
    assert len(text) <= telegram_channel.CAPTION_LIMIT


@pytest.mark.django_db
def test_prescription_medicine_post_is_reference_only():
    content = telegram_channel.build_post(_medicine(rx=True))
    text = content["text"]
    assert "Справочник лекарств · рецептурный препарат" in text
    assert "▫️ Действующее вещество: Клемастин" in text
    assert "▫️ Производитель: Haleon" in text
    assert "Цена в справочнике: <b>" in text
    assert telegram_channel.RX_NOTE in text
    assert content["button_text"] == "Открыть в справочнике"
    lowered = text.lower()
    for word in ("купить", "заказ", "доставка", "💰"):
        assert word not in lowered


@pytest.mark.django_db
def test_otc_medicine_post_has_no_trade_words():
    content = telegram_channel.build_post(_medicine(rx=False))
    text = content["text"]
    assert "Справочник лекарств · без рецепта" in text
    assert telegram_channel.OTC_NOTE in text
    assert content["button_text"] == "Открыть на сайте"
    for word in ("купить", "заказ", "доставка"):
        assert word not in text.lower()


@pytest.mark.django_db
def test_post_without_price_has_no_price_line():
    content = telegram_channel.build_post(_supplement(price=None))
    assert "Цена" not in content["text"]


@pytest.mark.django_db
def test_essential_oil_post():
    item = IncenseProduct.objects.create(**_fields("PHYTOIL Вода лавандовая, 250 мл"))
    text = telegram_channel.build_post(_base(item))["text"]
    assert "<b>PHYTOIL Вода лавандовая, 250 мл</b>" in text
    assert "Доставка из Турции: 7–14 дней" in text
    assert "Не является лекарством" not in text


@pytest.mark.django_db
def test_text_is_escaped_for_telegram_html():
    product = _supplement()
    SupplementProduct.objects.filter(base_product=product).update(
        name="A <b> & B", active_ingredient="x < y"
    )
    text = telegram_channel.build_post(Product.objects.get(pk=product.pk))["text"]
    assert "A &lt;b&gt; &amp; B" in text and "x &lt; y" in text


# ─── Фото ────────────────────────────────────────────────────────────────────


def _png() -> bytes:
    from PIL import Image

    output = io.BytesIO()
    Image.new("RGBA", (40, 30), (255, 0, 0, 128)).save(output, format="PNG")
    return output.getvalue()


def test_photo_is_converted_to_jpeg():
    with patch.object(telegram_channel, "_read_photo", return_value=_png()):
        assert telegram_channel.load_photo("https://cdn.example/x.png")[:3] == b"\xff\xd8\xff"


def test_seller_placeholder_photo_is_rejected(monkeypatch):
    raw = _png()
    monkeypatch.setattr(telegram_channel, "PLACEHOLDER_PHOTO_MD5", {hashlib.md5(raw).hexdigest()})
    with (
        patch.object(telegram_channel, "_read_photo", return_value=raw),
        pytest.raises(telegram_channel.ChannelPostError, match="заглушка"),
    ):
        telegram_channel.load_photo("https://cdn.example/x.png")


def test_missing_photo_is_rejected():
    with pytest.raises(telegram_channel.ChannelPostError, match="нет фото"):
        telegram_channel.load_photo("")


# ─── Публикация ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_publish_sends_photo_with_button(conf, telegram):
    post, _message = telegram_channel.enqueue(_supplement())
    assert telegram_channel.publish(post) == ""
    post.refresh_from_db()
    assert post.status == Status.PUBLISHED and post.message_id == 77
    assert post.post_url == "https://t.me/mudaroba_test/77" and post.published_at
    (token, method), kwargs = telegram.call_args
    assert (token, method) == ("token", "sendPhoto")
    assert kwargs["data"]["chat_id"] == "@mudaroba_test" and kwargs["data"]["parse_mode"] == "HTML"
    button = json.loads(kwargs["data"]["reply_markup"])["inline_keyboard"][0][0]
    assert (
        button["text"] == "Открыть на сайте"
        and "utm_source=telegram&utm_medium=channel" in button["url"]
    )
    assert kwargs["files"]["photo"][1] == b"jpeg"


@pytest.mark.django_db
def test_published_product_is_not_sent_again_until_returned(conf, telegram):
    product = _supplement()
    post, _message = telegram_channel.enqueue(product)
    telegram_channel.publish(post)
    assert telegram_channel.publish(post) != ""  # повторный вызов ничего не шлёт
    again, message = telegram_channel.enqueue(product)
    assert again.status == Status.PUBLISHED and "верните его в очередь" in message
    assert telegram.call_count == 1

    telegram_channel.requeue(again)
    assert telegram_channel.publish(again) == ""
    assert telegram.call_count == 2


@pytest.mark.django_db
def test_telegram_refusal_becomes_error_status(conf):
    post, _message = telegram_channel.enqueue(_supplement())
    refusal = _tg_response(ok=False, status=400, description="Bad Request: chat not found")
    with (
        patch("apps.orders.tasks._post_telegram", return_value=refusal),
        patch.object(telegram_channel, "load_photo", return_value=b"jpeg"),
    ):
        error = telegram_channel.publish(post)
    post.refresh_from_db()
    assert post.status == Status.ERROR and "chat not found" in post.error and error == post.error
    assert "token" not in post.error


@pytest.mark.django_db
def test_temporary_telegram_failure_keeps_post_queued(conf):
    post, _message = telegram_channel.enqueue(_supplement())
    with (
        patch("apps.orders.tasks._post_telegram", side_effect=TelegramTemporaryError("HTTP 502")),
        patch.object(telegram_channel, "load_photo", return_value=b"jpeg"),
    ):
        assert "временно недоступен" in telegram_channel.publish(post)
    post.refresh_from_db()
    assert post.status == Status.QUEUED and post.error


@pytest.mark.django_db
def test_unexpected_failure_does_not_raise(conf, telegram):
    post, _message = telegram_channel.enqueue(_supplement())
    with patch.object(telegram_channel, "build_post", side_effect=RuntimeError("boom")):
        assert telegram_channel.publish(post)
    post.refresh_from_db()
    assert post.status == Status.ERROR and "RuntimeError" in post.error
    assert not telegram.called


@pytest.mark.django_db
def test_import_restricted_medicine_is_published_with_label(conf, telegram):
    product = _medicine(rx=True)
    MedicineProduct.objects.filter(base_product=product).update(
        import_restricted_countries="KZ,RU,UZ"
    )
    post, _message = telegram_channel.enqueue(Product.objects.get(pk=product.pk))
    assert telegram_channel.publish(post) == ""
    post.refresh_from_db()
    assert post.status == Status.PUBLISHED
    caption = telegram.call_args.kwargs["data"]["caption"]
    assert (
        "⚠️ <b>Ввоз ограничен</b>: ввоз в Россию, Казахстан и Узбекистан запрещён или ограничен законом."
        in caption
    )
    assert telegram_channel.RX_NOTE in caption
    for word in ("купить", "заказ", "доставк"):
        assert word not in caption.lower()


@pytest.mark.django_db
def test_import_restriction_label_lists_only_marked_countries():
    product = _medicine()
    MedicineProduct.objects.filter(base_product=product).update(import_restricted_countries="KZ")
    text = telegram_channel.build_post(Product.objects.get(pk=product.pk))["text"]
    assert "⚠️ <b>Ввоз ограничен</b>: ввоз в Казахстан запрещён или ограничен законом." in text
    assert "Ввоз ограничен" not in telegram_channel.build_post(_medicine())["text"]


@pytest.mark.django_db
def test_product_hidden_after_queueing_is_not_published(conf, telegram):
    product = _supplement()
    post, _message = telegram_channel.enqueue(product)
    SupplementProduct.objects.filter(base_product=product).update(is_active=False)
    assert "скрыт" in telegram_channel.publish(post)
    post.refresh_from_db()
    assert post.status == Status.ERROR and not telegram.called


@pytest.mark.django_db
def test_publish_without_channel_keeps_post_queued(telegram):
    post, _message = telegram_channel.enqueue(_supplement())
    assert "Не указан канал" in telegram_channel.publish(post)
    post.refresh_from_db()
    assert post.status == Status.QUEUED and not telegram.called


# ─── Расписание ──────────────────────────────────────────────────────────────


def _at(hour, minute=0):
    return timezone.make_aware(datetime(2026, 11, 21, hour, minute))


@pytest.mark.django_db
def test_schedule_is_off_by_default(telegram):
    assert TelegramChannelSettings.load().enabled is False
    telegram_channel.enqueue(_supplement())
    assert telegram_channel.run_schedule(now=_at(10, 5)) == 0
    assert not telegram.called


@pytest.mark.django_db
def test_schedule_publishes_one_post_per_time(conf, telegram):
    first, _m = telegram_channel.enqueue(_supplement())
    second, _m = telegram_channel.enqueue(_supplement())
    TelegramChannelPost.objects.filter(pk=second.pk).update(position=0)
    TelegramChannelPost.objects.filter(pk=first.pk).update(position=5)

    assert telegram_channel.run_schedule(now=_at(9, 50)) == 0  # время ещё не настало
    with patch.object(telegram_channel.timezone, "now", return_value=_at(10, 1)):
        assert telegram_channel.run_schedule(now=_at(10, 1)) == 1
        assert telegram_channel.run_schedule(now=_at(10, 11)) == 0  # в это время пост уже ушёл
    second.refresh_from_db()
    first.refresh_from_db()
    assert second.status == Status.PUBLISHED and second.by_schedule  # меньший «Порядок» — раньше
    assert first.status == Status.QUEUED
    assert telegram_channel.run_schedule(now=_at(12, 0)) == 0  # между временами тихо
    with patch.object(telegram_channel.timezone, "now", return_value=_at(19, 0)):
        assert telegram_channel.run_schedule(now=_at(19, 0)) == 1
    assert telegram.call_count == 2


@pytest.mark.django_db
def test_schedule_skips_blocked_product_and_takes_next(conf, telegram):
    blocked = _supplement()
    bad, _m = telegram_channel.enqueue(blocked)
    good, _m = telegram_channel.enqueue(_supplement())
    SupplementProduct.objects.filter(base_product=blocked).update(is_active=False)
    assert telegram_channel.run_schedule(now=_at(10, 0)) == 1
    bad.refresh_from_db()
    good.refresh_from_db()
    assert bad.status == Status.ERROR and good.status == Status.PUBLISHED


@pytest.mark.django_db
def test_wrong_publish_times_are_rejected_in_admin_form():
    from django.core.exceptions import ValidationError

    conf = TelegramChannelSettings(publish_times="утром")
    with pytest.raises(ValidationError):
        conf.full_clean()
    assert telegram_channel.current_slot(conf, now=_at(10, 0)) is None


# ─── Админка ─────────────────────────────────────────────────────────────────


@pytest.fixture
def admin_client():
    user = User.objects.create_superuser(
        username=f"tg-{uuid4().hex[:8]}", email=f"{uuid4().hex[:8]}@example.test", password="x"
    )
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_admin_list_action_queues_products(admin_client):
    ok = _supplement()
    hidden = _supplement()
    SupplementProduct.objects.filter(base_product=hidden).update(is_active=False)
    ids = list(SupplementProduct.objects.values_list("pk", flat=True))
    response = admin_client.post(
        reverse("admin:catalog_supplementproduct_changelist"),
        {"action": "add_to_telegram_channel", "_selected_action": ids},
        follow=True,
    )
    assert response.status_code == 200
    assert list(TelegramChannelPost.objects.values_list("product_id", flat=True)) == [ok.pk]


@pytest.mark.django_db
def test_admin_product_page_previews_and_publishes(admin_client, conf, telegram):
    product = _supplement()
    url = reverse("admin:marketing_telegramchannelpost_product", args=[product.pk])
    page = admin_client.get(url)
    assert page.status_code == 200
    html = page.content.decode()
    assert "Опубликовать сейчас" in html and "INOVIT Витамин D3" in html and not telegram.called

    assert admin_client.post(url, {"action": "queue"}).status_code == 302
    assert TelegramChannelPost.objects.get(product=product).status == Status.QUEUED
    assert admin_client.post(url, {"action": "publish"}).status_code == 302
    assert TelegramChannelPost.objects.get(product=product).status == Status.PUBLISHED
    admin_client.post(url, {"action": "publish"})  # уже опубликован — второй раз не уходит
    assert telegram.call_count == 1


@pytest.mark.django_db
def test_admin_product_card_has_channel_button(admin_client):
    product = _supplement()
    item = SupplementProduct.objects.get(base_product=product)
    page = admin_client.get(reverse("admin:catalog_supplementproduct_change", args=[item.pk]))
    assert page.status_code == 200
    assert (
        reverse("admin:marketing_telegramchannelpost_product", args=[product.pk])
        in page.content.decode()
    )


@pytest.mark.django_db
def test_admin_queue_and_settings_pages_open(admin_client, conf):
    telegram_channel.enqueue(_supplement())
    assert (
        admin_client.get(reverse("admin:marketing_telegramchannelpost_changelist")).status_code
        == 200
    )
    assert (
        admin_client.get(
            reverse("admin:marketing_telegramchannelsettings_changelist"), follow=True
        ).status_code
        == 200
    )


def _channel_rows(admin_client, value=""):
    """Товары списка «БАДы» в админке с фильтром «Telegram-канал»."""
    url = reverse("admin:catalog_supplementproduct_changelist")
    response = admin_client.get(url, {"telegram_channel": value} if value else {})
    assert response.status_code == 200
    return response, {item.base_product_id for item in response.context["cl"].result_list}


@pytest.mark.django_db
def test_admin_list_column_and_filter_show_channel_state(admin_client, conf, telegram):
    never, queued, published, failed = (_supplement() for _ in range(4))
    telegram_channel.enqueue(queued)
    done, _m = telegram_channel.enqueue(published)
    telegram_channel.publish(done)
    bad, _m = telegram_channel.enqueue(failed)
    TelegramChannelPost.objects.filter(pk=bad.pk).update(status=Status.ERROR, error="нет фото")

    response, everything = _channel_rows(admin_client)
    assert everything == {never.pk, queued.pk, published.pk, failed.pk}
    html = response.content.decode()
    date = timezone.localtime(TelegramChannelPost.objects.get(pk=done.pk).published_at)
    link = f'<a href="https://t.me/mudaroba_test/77" target="_blank" rel="noopener noreferrer">Опубликован {date:%d.%m.%Y}</a>'
    assert link in html
    assert "column-telegram_channel_status" in html and "В очереди" in html and "Ошибка" in html
    for label in ("Не публиковался", "В очереди", "Опубликован", "Ошибка"):
        assert label in html  # пункты фильтра

    assert _channel_rows(admin_client, "none")[1] == {never.pk}
    assert _channel_rows(admin_client, "queued")[1] == {queued.pk}
    assert _channel_rows(admin_client, "published")[1] == {published.pk}
    assert _channel_rows(admin_client, "error")[1] == {failed.pk}


@pytest.mark.django_db
def test_admin_list_column_does_not_query_per_row(admin_client, django_assert_num_queries):
    from django.contrib import admin as django_admin

    telegram_channel.enqueue(_supplement())
    telegram_channel.enqueue(_supplement())
    _supplement()
    model_admin = django_admin.site._registry[SupplementProduct]
    items = list(
        _channel_rows(admin_client)[0].context["cl"].result_list
    )  # строки настоящего списка
    assert len(items) == 3
    with django_assert_num_queries(0):
        values = [model_admin.telegram_channel_status(item) for item in items]
    assert sorted(values) == ["В очереди", "В очереди", "—"]
