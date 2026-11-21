"""Telegram-канал: пост из карточки товара, очередь и публикация (docs/TELEGRAM_CHANNEL.md).

Текст поста собирается кодом из тех же данных, что видит посетитель карточки (сериализатор
витрины: название и цена в рублях на день публикации). Вид поста выбран владельцем 21.11.2026:
«с фактами»; у лекарств пост справочный — без «купить», «заказать» и строки о доставке.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
from datetime import datetime, timedelta
from html import unescape
from urllib.parse import parse_qs, urlsplit

import requests
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.files.storage import default_storage
from django.utils import timezone
from django.utils.html import escape, strip_tags

from .models import TelegramChannelPost, TelegramChannelSettings, parse_publish_times

logger = logging.getLogger(__name__)

# Разделы, которые идут в канал: лекарства, БАДы, эфирные масла (раздел типа incense).
DOMAIN_ACCESSORS = {
    "medicines": "medicine_item",
    "supplements": "supplement_item",
    "incense": "incense_item",
}
CAPTION_LIMIT = 1024
DESCRIPTION_LIMIT = 300
# Заглушка ilacfiyati «Görsel hazırlanıyor» (чужая коробка «Antibiotic 250mg») вместо фото товара:
# 21.11.2026 она стояла у 14 из 40 проверенных эфирных масел. В канал такой товар не уходит.
PLACEHOLDER_PHOTO_MD5 = {"8be360ab174bf3d7d1c7f6a85f775eff"}
# Окно после времени публикации, в котором расписание ещё отправляет пост (задача идёт раз в 10 минут).
SLOT_WINDOW = timedelta(minutes=30)
# Сколько товаров из очереди расписание пробует за один запуск, если первые не прошли проверку.
SLOT_ATTEMPTS = 3

SUPPLEMENT_NOTE = "БАД. Не является лекарством."
OTC_NOTE = "Информация справочная. Перед применением посоветуйтесь с врачом."
RX_NOTE = "Справочная информация, не реклама. Применяется только по назначению врача."
# Абзац-оговорка в описании БАДа: в посте вместо него SUPPLEMENT_NOTE.
_DISCLAIMER_RE = re.compile(r"не является лекарств", re.IGNORECASE)
_SENTENCE_END_RE = re.compile(r"(?<=[.!?…])\s+")


class ChannelPostError(Exception):
    """Товар нельзя опубликовать; текст — причина для владельца."""


def domain_item(product):
    """Запись раздела (лекарство, БАД, масло) товара или None."""
    accessor = DOMAIN_ACCESSORS.get(str(product.product_type or "").replace("-", "_"))
    return getattr(product, accessor, None) if accessor else None


def block_reason(product) -> str:
    """Почему товар не идёт в канал; пусто — можно."""
    from apps.catalog.admin_links import product_site_url

    if str(product.product_type or "").replace("-", "_") not in DOMAIN_ACCESSORS:
        return "В канал идут только лекарства, БАДы и эфирные масла."
    item = domain_item(product)
    if item is None or not product_site_url(item):
        return "Товар скрыт на сайте — у него нет страницы."
    return ""


def enqueue(product) -> tuple[TelegramChannelPost | None, str]:
    """Ставит товар в очередь. Возвращает (пост, сообщение); пост None — товар не подходит."""
    reason = block_reason(product)
    if reason:
        return None, reason
    post, created = TelegramChannelPost.objects.get_or_create(product=product)
    if created:
        return post, "Поставлен в очередь."
    if post.status == TelegramChannelPost.Status.ERROR:
        requeue(post)
        return post, "Снова поставлен в очередь."
    if post.status == TelegramChannelPost.Status.PUBLISHED:
        return (
            post,
            "Уже опубликован. Чтобы отправить ещё раз, верните его в очередь в разделе очереди.",
        )
    return post, "Уже в очереди."


def requeue(post: TelegramChannelPost) -> None:
    """Возвращает пост в очередь (после ошибки или для повторной публикации) — в конец."""
    post.status = TelegramChannelPost.Status.QUEUED
    post.queued_at = timezone.now()
    post.error = ""
    post.save(update_fields=["status", "queued_at", "error"])


# ─── Текст поста ─────────────────────────────────────────────────────────────


def _card(item) -> dict:
    """Карточка, как её отдаёт сайт: русское название, цена в рублях с наценкой."""
    from apps.catalog.serializers import serialize_product_for_card
    from apps.orders.cart_reminders import _SiteRequest

    return dict(serialize_product_for_card(item, _SiteRequest(AnonymousUser(), "RUB", "ru")))


def _clean(value) -> str:
    """Значение поля карточки одной строкой (название и факты — не HTML, теги в них не вырезаются)."""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _plain(value) -> str:
    """Текст из HTML описания."""
    return _clean(unescape(strip_tags(str(value or ""))))


def _short_description(html: str) -> str:
    """Первые предложения описания без оговорки «не является лекарством», до DESCRIPTION_LIMIT знаков."""
    paragraphs = re.split(r"</p>|<br\s*/?>|\n", str(html or ""), flags=re.IGNORECASE)
    sentences = []
    for paragraph in paragraphs:
        text = _plain(paragraph)
        if text and not _DISCLAIMER_RE.search(text):
            sentences.extend(_SENTENCE_END_RE.split(text))
    result = ""
    for sentence in sentences:
        candidate = f"{result} {sentence}".strip()
        if len(candidate) > DESCRIPTION_LIMIT:
            break
        result = candidate
    return result


def _hashtag(name: str) -> str:
    words = re.findall(r"[0-9A-Za-zА-Яа-яЁё]+", name or "")
    return "#" + "".join(word[:1].upper() + word[1:] for word in words) if words else ""


# Как на карточке сайта (frontend/src/lib/importRestriction.js): порядок стран и винительный падеж.
_RESTRICTED_COUNTRIES = (("RU", "Россию"), ("KZ", "Казахстан"), ("UZ", "Узбекистан"))


def import_restriction_line(item) -> str:
    """Метка «Ввоз ограничен» со странами — тем же текстом, что на карточке; пусто — метки нет.

    Решение владельца 21.11.2026: такие лекарства в канал идут, пост несёт метку. Полная плашка
    карточки («Доставку… не выполняем…», «Купить можно…») в пост не переносится: у лекарств в канале
    нет слов о покупке и доставке.
    """
    codes = set(str(getattr(item, "import_restricted_countries", "") or "").split(","))
    names = [name for code, name in _RESTRICTED_COUNTRIES if code in codes]
    if not names:
        return ""
    countries = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} и {names[-1]}"
    return f"⚠️ <b>Ввоз ограничен</b>: ввоз в {countries} запрещён или ограничен законом."


def _category_names(card: dict) -> list[str]:
    category = card.get("category") or {}
    names = [(ancestor or {}).get("name") for ancestor in category.get("ancestors") or []]
    names.append(category.get("name"))
    return [name for name in names if name]


def _fact(label: str, value) -> str:
    text = _clean(value)
    return f"▫️ {label}: {escape(text, quote=False)}" if text else ""


def product_url(product) -> str:
    """Адрес карточки с UTM-меткой канала."""
    from apps.catalog.services.product_resolve import build_canonical_path
    from apps.orders.cart_reminders import site_url

    path = build_canonical_path(product.product_type, product.slug)
    return f"{(site_url() or 'https://mudaroba.com').rstrip('/')}{path}?utm_source=telegram&utm_medium=channel"


def build_post(product, today=None) -> dict:
    """Пост товара: text (HTML для Telegram), button_text, url, photo (адрес или путь фото карточки)."""
    from apps.catalog.services import delivery_terms
    from apps.orders.cart_reminders import format_money

    item = domain_item(product)
    card = _card(item)
    product_type = str(product.product_type or "").replace("-", "_")
    is_medicine = product_type == "medicines"
    is_rx = is_medicine and bool(card.get("prescription_required"))
    name = escape(_clean(card.get("name") or product.name), quote=False)
    brand = (card.get("brand") or {}).get("name")
    categories = _category_names(card)
    date_text = (today or timezone.localdate()).strftime("%d.%m.%Y")

    if is_medicine:
        title = f"📋 <b>{name}</b>" if is_rx else f"<b>{name}</b>"
        subtitle = "Справочник лекарств · " + ("рецептурный препарат" if is_rx else "без рецепта")
        form = ", ".join(
            part
            for part in (_clean(card.get("dosage_form")).lower(), _clean(card.get("volume")))
            if part
        )
        facts = [
            _fact("Действующее вещество", card.get("active_ingredient")),
            _fact("Форма", form),
            _fact("Производитель", card.get("manufacturer") or brand),
        ]
        note = RX_NOTE if is_rx else OTC_NOTE
        hashtags = ""
    elif product_type == "supplements":
        title = f"<b>{name}</b>"
        section = [name for name in categories[-1:] if name != "БАДы"]
        subtitle = " · ".join(["БАД", *section])
        facts = [
            _fact("Состав", card.get("active_ingredient")),
            _fact("Производитель", brand),
            f"▫️ Доставка из Турции: {delivery_terms.SHORT['ru']}",
        ]
        note = SUPPLEMENT_NOTE
        hashtags = " ".join(["#БАДы", *[_hashtag(name) for name in section]])
    else:
        title = f"<b>{name}</b>"
        subtitle = " · ".join(dict.fromkeys(categories[-2:]))
        facts = [_fact("Производитель", brand), "▫️ Доставка из Турции: 7–14 дней"]
        note = ""
        hashtags = " ".join(_hashtag(name) for name in dict.fromkeys(categories[-2:]))

    price_line = ""
    try:
        price = float(card.get("price") or 0)
    except (TypeError, ValueError):
        price = 0
    if price > 0:
        money = format_money(card["price"], card.get("currency") or "RUB", "ru")
        if is_rx:
            price_line = f"Цена в справочнике: <b>{money}</b> (на {date_text})"
        else:
            price_line = f"💰 Цена: <b>{money}</b> (на {date_text})"

    tail = "\n".join(part for part in (f"<i>{note}</i>" if note else "", hashtags) if part)
    blocks = [
        "\n".join(part for part in (title, escape(subtitle, quote=False)) if part),
        "\n".join(fact for fact in facts if fact),
        escape(_short_description(card.get("description")), quote=False),
        price_line,
        import_restriction_line(item) if is_medicine else "",
        tail,
    ]
    text = "\n\n".join(block for block in blocks if block)
    if (
        len(text) > CAPTION_LIMIT
    ):  # длинное название и факты: описание — первое, чем можно пожертвовать
        blocks[2] = ""
        text = "\n\n".join(block for block in blocks if block)
    return {
        "text": text,
        "button_text": "Открыть в справочнике" if is_rx else "Открыть на сайте",
        "url": product_url(product),
        "photo": card.get("main_image_url") or card.get("main_image") or "",
    }


# ─── Фото ────────────────────────────────────────────────────────────────────


def _read_photo(source: str) -> bytes:
    """Файл фото карточки: из хранилища по пути proxy-media, иначе по прямому адресу."""
    parts = urlsplit(source)
    path = (parse_qs(parts.query).get("path") or [""])[0]
    if "proxy-media" in parts.path and path:
        with default_storage.open(path, "rb") as handle:
            return handle.read()
    if not source.startswith("http"):
        raise ChannelPostError("У товара нет фото.")
    response = requests.get(source, timeout=20)
    response.raise_for_status()
    return response.content


def load_photo(source: str) -> bytes:
    """JPEG до 1280 px для sendPhoto (webp и png Telegram показывает не везде как фото)."""
    from PIL import Image

    if not source:
        raise ChannelPostError("У товара нет фото.")
    try:
        raw = _read_photo(source)
    except ChannelPostError:
        raise
    except Exception as exc:
        raise ChannelPostError(f"Фото товара не открылось ({type(exc).__name__}).") from None
    if hashlib.md5(raw).hexdigest() in PLACEHOLDER_PHOTO_MD5:
        raise ChannelPostError("Вместо фото у товара заглушка продавца — нужно настоящее фото.")
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except Exception:
        raise ChannelPostError("Фото товара не читается как картинка.") from None
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[-1])
        image = background
    else:
        image = image.convert("RGB")
    image.thumbnail((1280, 1280))
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=88)
    return output.getvalue()


# ─── Публикация ──────────────────────────────────────────────────────────────


def _post_link(result: dict) -> str:
    chat = result.get("chat") or {}
    message_id = result.get("message_id")
    if not message_id:
        return ""
    if chat.get("username"):
        return f"https://t.me/{chat['username']}/{message_id}"
    chat_id = str(chat.get("id") or "")
    return (
        f"https://t.me/c/{chat_id.removeprefix('-100')}/{message_id}"
        if chat_id.startswith("-100")
        else ""
    )


def _fail(post: TelegramChannelPost, error: str, *, keep_queued: bool = False) -> str:
    post.status = (
        TelegramChannelPost.Status.QUEUED if keep_queued else TelegramChannelPost.Status.ERROR
    )
    post.error = error[:1000]
    post.save(update_fields=["status", "error"])
    return error


def publish(post: TelegramChannelPost, *, by_schedule: bool = False) -> str:
    """Публикует пост в канал. Возвращает "" при успехе, иначе текст ошибки (он же записан в пост).

    Исключений не бросает: ошибка Telegram или карточки — это статус поста, а не падение задачи.
    Временный сбой (сеть, 429, 5xx) оставляет пост в очереди.
    """
    from apps.orders.tasks import TelegramTemporaryError, _post_telegram

    statuses = (TelegramChannelPost.Status.QUEUED, TelegramChannelPost.Status.ERROR)
    claimed = TelegramChannelPost.objects.filter(pk=post.pk, status__in=statuses).update(
        status=TelegramChannelPost.Status.SENDING
    )
    if not claimed:
        return "Пост уже опубликован или отправляется прямо сейчас."
    post.refresh_from_db()
    conf = TelegramChannelSettings.load()
    bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
    channel = (conf.channel_id or "").strip()
    if not bot_token or not channel:
        return _fail(post, "Не указан канал в настройках или у сайта нет бота.", keep_queued=True)
    try:
        product = post.product
        reason = block_reason(product)
        if reason:
            return _fail(post, reason)
        content = build_post(product)
        photo = load_photo(content["photo"])
        markup = {"inline_keyboard": [[{"text": content["button_text"], "url": content["url"]}]]}
        response = _post_telegram(
            bot_token,
            "sendPhoto",
            data={
                "chat_id": channel,
                "caption": content["text"],
                "parse_mode": "HTML",
                "reply_markup": json.dumps(markup, ensure_ascii=False),
            },
            files={"photo": ("photo.jpg", photo, "image/jpeg")},
            timeout=30,
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if not response.ok or not payload.get("ok"):
            description = payload.get("description") or f"HTTP {response.status_code}"
            return _fail(post, f"Telegram не принял пост: {description}")
    except ChannelPostError as exc:
        return _fail(post, str(exc))
    except TelegramTemporaryError as exc:
        return _fail(
            post, f"Telegram временно недоступен ({exc}). Пост остался в очереди.", keep_queued=True
        )
    except Exception as exc:  # задача расписания не должна падать из-за одной карточки
        logger.exception("Telegram channel post %s failed", post.pk)
        return _fail(post, f"Не удалось собрать или отправить пост: {type(exc).__name__}")
    result = payload.get("result") or {}
    post.status = TelegramChannelPost.Status.PUBLISHED
    post.published_at = timezone.now()
    post.by_schedule = by_schedule
    post.message_id = result.get("message_id")
    post.post_url = _post_link(result)
    post.error = ""
    post.save(
        update_fields=["status", "published_at", "by_schedule", "message_id", "post_url", "error"]
    )
    return ""


def current_slot(conf: TelegramChannelSettings, now=None):
    """Начало времени публикации, в окне которого мы сейчас, или None."""
    now = timezone.localtime(now or timezone.now())
    try:
        times = parse_publish_times(conf.publish_times)
    except ValueError:
        return None
    for slot_time in reversed(times):
        start = timezone.make_aware(datetime.combine(now.date(), slot_time), now.tzinfo)
        if start <= now < start + SLOT_WINDOW:
            return start
    return None


def run_schedule(now=None) -> int:
    """Один пост из очереди на каждое время публикации. Возвращает число опубликованных (0 или 1)."""
    conf = TelegramChannelSettings.load()
    if not conf.enabled:
        return 0
    slot = current_slot(conf, now)
    if slot is None:
        return 0
    if TelegramChannelPost.objects.filter(by_schedule=True, published_at__gte=slot).exists():
        return 0
    queue = TelegramChannelPost.objects.filter(
        status=TelegramChannelPost.Status.QUEUED
    ).select_related("product")
    for post in queue[:SLOT_ATTEMPTS]:
        publish(post, by_schedule=True)
        post.refresh_from_db()
        if post.status == TelegramChannelPost.Status.PUBLISHED:
            return 1
        if (
            post.status == TelegramChannelPost.Status.QUEUED
        ):  # временный сбой — повтор в следующий запуск
            return 0
    return 0
