"""Напоминания клиенту о неотправленном Списке заявки (брошенная корзина): email и Telegram.

Кому, когда и что пишем — docs/CART_REMINDERS.md. Включаются и настраиваются в админке
(CartReminderSettings), по умолчанию выключены.
"""
from __future__ import annotations

import html
import logging
import time
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import parse_qs, urlencode, urlsplit

import requests
from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.db.models import Exists, F, OuterRef, Q
from django.template.loader import render_to_string
from django.utils import timezone

from apps.catalog.services.product_resolve import build_canonical_path
from apps.users.telegram_auth import CART_REMINDERS_OFF_CALLBACK

from .models import Cart, CartItem, CartReminderLog, CartReminderSettings, Order, SourcingRequest

logger = logging.getLogger(__name__)

MAX_STEPS = 2
# Сколько позиций показываем в сообщении; остальные — «и ещё N»
MAX_LISTED_ITEMS = 10
# Задача ежечасная: не занимаем воркер дольше, остаток уйдёт в следующий запуск
RUN_TIME_BUDGET_SECONDS = 10 * 60
UNSUBSCRIBE_SALT = "orders.cart-reminders.unsubscribe"
CLICK_SALT = "orders.cart-reminders.click"
PLACEHOLDER_EMAIL_SUFFIX = "@mudaroba.local"

_CENT_CURRENCIES = {"USD", "EUR", "USDT"}
_CURRENCY_SYMBOLS = {"RUB": "₽", "USD": "$", "EUR": "€", "TRY": "₺", "KZT": "₸", "USDT": "₮"}

# Тексты нейтральные: сайт не продаёт лекарства — «заявка», «консультация», «подбор», без «купить».
LABELS = {
    "ru": {
        "subject": {
            0: "Тест: ваш Список заявки ждёт",
            1: "Ваш Список заявки ждёт",
            2: "Товары в Списке заявки всё ещё ждут вас",
        },
        "intro": "Вы добавили товары в Список заявки, но ещё не отправили его менеджеру.",
        "next_step": "Отправьте заявку — менеджер уточнит наличие, итоговую цену и доставку и свяжется с вами.",
        "prices_note": "Цены — на {date} по текущему курсу. Итоговую сумму и доставку менеджер подтвердит по заявке.",
        "help": "Нужна консультация или помощь с подбором? Напишите менеджеру — ответим на вопросы о товарах, наличии и доставке.",
        "qty": "Количество",
        "total": "Итого",
        "more_items": "и ещё {count}",
        "cta_checkout": "Отправить заявку",
        "cta_cart": "Открыть Список заявки",
        "cta_manager": "Связаться с менеджером",
        "reason": "Вы получили это письмо, потому что у вас есть аккаунт на mudaroba.com и в вашем Списке заявки остались товары.",
        "unsubscribe": "Не присылать напоминания",
        "profile": "Настройки уведомлений в профиле",
        "tg_stop": "🔕 Не присылать напоминания",
        "tg_stop_hint": "Отключить напоминания: /stop",
    },
    "en": {
        "subject": {
            0: "Test: your request list is waiting",
            1: "Your request list is waiting",
            2: "Items in your request list are still waiting for you",
        },
        "intro": "You added items to your request list but haven't sent it to a manager yet.",
        "next_step": "Send the request and a manager will confirm availability, the final price and delivery and get in touch.",
        "prices_note": "Prices as of {date} at the current exchange rate. A manager will confirm the final total and delivery.",
        "help": "Need advice or help choosing? Message a manager — we'll answer questions about the products, availability and delivery.",
        "qty": "Quantity",
        "total": "Total",
        "more_items": "and {count} more",
        "cta_checkout": "Send request",
        "cta_cart": "Open request list",
        "cta_manager": "Contact a manager",
        "reason": "You received this email because you have an account on mudaroba.com and there are items left in your request list.",
        "unsubscribe": "Stop these reminders",
        "profile": "Notification settings in your profile",
        "tg_stop": "🔕 Stop these reminders",
        "tg_stop_hint": "Stop reminders: /stop",
    },
}


def normalize_locale(value: str | None) -> str:
    return "en" if (value or "").strip().lower().startswith("en") else "ru"


def site_url() -> str:
    return (getattr(settings, "FRONTEND_SITE_URL", "") or getattr(settings, "SITE_URL", "")).rstrip("/")


def has_confirmed_email(user) -> bool:
    email = (getattr(user, "email", "") or "").strip().lower()
    return bool(
        email
        and getattr(user, "is_verified", False)
        and getattr(user, "email_notifications", True)
        and not email.endswith(PLACEHOLDER_EMAIL_SUFFIX)
    )


def has_telegram(user) -> bool:
    return bool(
        (getattr(user, "telegram_id", "") or "").strip()
        and getattr(user, "telegram_notifications", False)
        and getattr(settings, "TELEGRAM_BOT_TOKEN", "")
    )


def format_money(value, currency: str, locale: str) -> str:
    """Как formatMoney во frontend/src/lib/price.ts: копейки только у USD/EUR/USDT."""
    code = (currency or "").upper()
    digits = 2 if code in _CENT_CURRENCIES else 0
    amount = Decimal(str(value or 0)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    text = f"{amount:,.{digits}f}"
    if locale == "ru":
        text = text.replace(",", " ").replace(".", ",")
    return f"{text} {_CURRENCY_SYMBOLS.get(code, code)}"


# ─── Кому и когда ────────────────────────────────────────────────────────────


def _channels_q(conf: CartReminderSettings) -> Q | None:
    """Клиенты, которым есть куда написать: подтверждённый email и/или привязанный Telegram."""
    channels = []
    if conf.email_enabled:
        channels.append(
            Q(user__is_verified=True, user__email_notifications=True)
            & ~Q(user__email="")
            & ~Q(user__email__iendswith=PLACEHOLDER_EMAIL_SUFFIX)
        )
    if conf.telegram_enabled and getattr(settings, "TELEGRAM_BOT_TOKEN", ""):
        channels.append(Q(user__telegram_notifications=True) & ~Q(user__telegram_id=""))
    if not channels:
        return None
    combined = channels[0]
    for extra in channels[1:]:
        combined |= extra
    return combined


def due_carts(conf: CartReminderSettings, now=None):
    """Корзины вошедших клиентов, которым пора отправить очередное напоминание.

    Круг напоминаний — пока корзина не менялась после последнего напоминания
    (reminder_sent_at >= updated_at). Первое — через first_delay_hours простоя, второе —
    через second_delay_hours от того же изменения; новый круг (корзина снова менялась) —
    не раньше pause_days после прошлого напоминания. Клиент, отправивший после изменения
    корзины заявку или «Найдём товар», напоминаний не получает.
    """
    now = now or timezone.now()
    channels = _channels_q(conf)
    if channels is None:
        return Cart.objects.none()

    in_cycle = Q(reminder_sent_at__gte=F("updated_at"))
    due = (
        (Q(reminder_sent_at__isnull=True) | Q(reminder_sent_at__lt=F("updated_at")))
        & Q(updated_at__lte=now - timedelta(hours=conf.first_delay_hours))
        & (Q(reminder_sent_at__isnull=True) | Q(reminder_sent_at__lte=now - timedelta(days=conf.pause_days)))
    )
    if conf.second_delay_hours:
        due |= in_cycle & Q(
            reminder_count=1,
            updated_at__lte=now - timedelta(hours=conf.second_delay_hours),
        )

    return (
        Cart.objects.filter(
            user__isnull=False,
            user__is_active=True,
            user__cart_reminders_enabled=True,
            updated_at__gte=now - timedelta(days=conf.max_age_days),
        )
        .filter(channels)
        .filter(due)
        .filter(Exists(CartItem.objects.filter(cart_id=OuterRef("pk"))))
        .exclude(Exists(Order.objects.filter(user_id=OuterRef("user_id"), created_at__gte=OuterRef("updated_at"))))
        .exclude(
            Exists(SourcingRequest.objects.filter(user_id=OuterRef("user_id"), created_at__gte=OuterRef("updated_at")))
        )
        .order_by("updated_at")
    )


def _claim_step(cart: Cart, now) -> int | None:
    """Атомарно занимает очередной шаг круга: при гонке двух запусков сообщение уйдёт один раз."""
    in_cycle = cart.reminder_sent_at is not None and cart.reminder_sent_at >= cart.updated_at
    step = cart.reminder_count + 1 if in_cycle else 1
    if step > MAX_STEPS:
        return None
    claimed = Cart.objects.filter(
        pk=cart.pk,
        updated_at=cart.updated_at,
        reminder_sent_at=cart.reminder_sent_at,
        reminder_count=cart.reminder_count,
    ).update(reminder_sent_at=now, reminder_count=step)
    return step if claimed == 1 else None


def run_cart_reminders(batch_size: int = 50, now=None) -> int:
    """Отправляет напоминания пачкой; возвращает число корзин, по которым что-то доставлено."""
    conf = CartReminderSettings.load()
    if not conf.enabled:
        return 0
    now = now or timezone.now()
    started = time.monotonic()
    delivered = 0
    cart_ids = list(due_carts(conf, now).values_list("pk", flat=True)[:batch_size])
    for cart_id in cart_ids:
        if time.monotonic() - started > RUN_TIME_BUDGET_SECONDS:
            break
        try:
            # Перепроверяем на свежей строке: корзина могла измениться после отбора
            cart = due_carts(conf, now).filter(pk=cart_id).select_related("user").first()
            if cart is None:
                continue
            step = _claim_step(cart, now)
            if step is None:
                continue
            logs = send_reminder(cart.user, step, conf, cart=cart)
            delivered += int(any(log.status == CartReminderLog.Status.SENT for log in logs))
        except Exception:
            # Одна сломанная корзина не останавливает пачку и не роняет задачу
            logger.exception("Cart reminder failed for cart %s", cart_id)
    return delivered


# ─── Содержимое: позиции по актуальным ценам ────────────────────────────────


class _SiteRequest:
    """Минимум интерфейса request для CartItemSerializer вне HTTP-запроса: валюта и адрес сайта."""

    def __init__(self, user, currency: str, locale: str):
        parsed = urlsplit(site_url() or "https://mudaroba.com")
        self.scheme = parsed.scheme or "https"
        self._host = parsed.netloc
        self.headers = {"X-Currency": (currency or "RUB").upper()}
        self.query_params = {}
        self.user = user
        self.LANGUAGE_CODE = locale

    def get_host(self) -> str:
        return self._host

    def build_absolute_uri(self, location: str) -> str:
        if location.startswith("http"):
            return location
        return f"{self.scheme}://{self._host}/{location.lstrip('/')}"


def _email_image_url(url: str | None) -> str | None:
    """В письмо — прямой адрес CDN, а не proxy-image через Django."""
    if not url:
        return None
    parts = urlsplit(url)
    if parts.path.rstrip("/").endswith("/api/catalog/proxy-image"):
        original = (parse_qs(parts.query).get("url") or [""])[0]
        if original.startswith("https://"):
            return original
    return url if url.startswith("http") else None


def _localized_name(serializer, item, locale: str) -> str:
    for translation in serializer.get_product_translations(item) or []:
        if translation.get("locale") == locale and (translation.get("name") or "").strip():
            return translation["name"].strip()
    return serializer.get_product_name(item) or ""


def _item_path(serializer, item) -> str:
    """Как getProductLink в pages/cart.tsx: родитель + ?active_variant_slug, иначе сам slug."""
    base_slug = serializer.get_product_parent_slug(item) or serializer.get_product_slug(item)
    if not base_slug:
        return "/cart"
    path = build_canonical_path(item.product.product_type or "medicines", base_slug)
    params = {}
    variant_slug = (serializer.get_product_variant_slug(item) or "").strip()
    if variant_slug:
        params["active_variant_slug"] = variant_slug
    if (item.chosen_size or "").strip():
        params["favorite_size"] = item.chosen_size.strip()
    return f"{path}?{urlencode(params)}" if params else path


def build_reminder_content(user, items, currency: str, locale: str) -> dict:
    """Позиции с ценами на момент отправки — те же, что видит клиент в корзине."""
    from .serializers import CartItemSerializer

    request = _SiteRequest(user, currency, locale)
    serializer = CartItemSerializer(context={"request": request})
    currency = serializer.get_currency(None)
    lines = []
    total = Decimal("0")
    for item in items:
        price = Decimal(str(serializer.get_price(item) or 0))
        line_total = (price * item.quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if item.is_payable:
            total += line_total
        lines.append(
            {
                "name": _localized_name(serializer, item, locale),
                "quantity": item.quantity,
                "size": item.chosen_size or "",
                "price_text": format_money(price, currency, locale),
                "total_text": format_money(line_total, currency, locale),
                "image_url": _email_image_url(serializer.get_product_image_url(item)),
                "path": _item_path(serializer, item),
            }
        )
    return {
        "locale": locale,
        "items": lines,
        "items_count": sum(line["quantity"] for line in lines),
        "total": total,
        "currency": currency,
        "total_text": format_money(total, currency, locale),
    }


def _cart_items(cart: Cart) -> list:
    from .views import _get_cart_with_prefetch

    return list(_get_cart_with_prefetch(cart).items.all())


# ─── Ссылки: UTM, переходы, отписка ─────────────────────────────────────────


def _with_utm(path: str, channel: str, step: int, content: str) -> str:
    utm = urlencode(
        {
            "utm_source": "cart_reminder",
            "utm_medium": channel,
            "utm_campaign": f"cart_reminder_{step}" if step else "cart_reminder_test",
            "utm_content": content,
        }
    )
    return f"{path}{'&' if '?' in path else '?'}{utm}"


def _localized_path(path: str, locale: str) -> str:
    return f"/en{path}" if locale == "en" else path


def _tracked_link(log: CartReminderLog, path: str, content: str, locale: str) -> str:
    """Ссылка через счётчик переходов: в журнале видно, что клиент открыл сайт из напоминания."""
    target = _with_utm(_localized_path(path, locale), log.channel, log.step, content)
    token = signing.dumps([log.pk, target], salt=CLICK_SALT, compress=True)
    return f"{site_url()}/api/orders/cart-reminders/go/?{urlencode({'t': token})}"


def resolve_click_token(token: str) -> tuple[int | None, str]:
    """(id записи журнала, путь на сайте); недействительный токен ведёт на главную."""
    try:
        log_id, path = signing.loads(token or "", salt=CLICK_SALT)
    except (signing.BadSignature, TypeError, ValueError):
        return None, "/"
    if not isinstance(path, str) or not path.startswith("/") or path.startswith("//") or "\\" in path:
        return None, "/"
    return (log_id if isinstance(log_id, int) else None), path


def unsubscribe_token(user, locale: str) -> str:
    return signing.dumps({"u": user.pk, "l": locale}, salt=UNSUBSCRIBE_SALT)


def read_unsubscribe_token(token: str) -> dict | None:
    try:
        data = signing.loads(token or "", salt=UNSUBSCRIBE_SALT)
    except (signing.BadSignature, TypeError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("u"), int):
        return None
    return {"user_id": data["u"], "locale": normalize_locale(data.get("l"))}


def unsubscribe_url(user, locale: str) -> str:
    return f"{site_url()}/api/orders/cart-reminders/unsubscribe/?{urlencode({'t': unsubscribe_token(user, locale)})}"


def _manager_url() -> str:
    """Контакт менеджера из «Настроек футера»: Telegram, иначе WhatsApp."""
    try:
        from apps.settings.models import FooterSettings

        footer = FooterSettings.objects.first()
    except Exception:
        footer = None
    if footer is None:
        return ""
    return (footer.telegram_url or footer.whatsapp_url or "").strip()


# ─── Отправка ────────────────────────────────────────────────────────────────


def _new_log(user, cart, step, channel, recipient, content) -> CartReminderLog:
    return CartReminderLog.objects.create(
        user=user,
        cart=cart,
        step=step,
        channel=channel,
        recipient=recipient[:254],
        items_count=content["items_count"],
        total=content["total"],
        currency=content["currency"],
    )


def _finish_log(log: CartReminderLog, error: str = "") -> None:
    log.status = CartReminderLog.Status.FAILED if error else CartReminderLog.Status.SENT
    log.error = error[:300]
    log.save(update_fields=["status", "error"])


def render_email(user, content: dict, log: CartReminderLog) -> tuple[str, str, str]:
    """(тема, текст, html) письма-напоминания."""
    locale = content["locale"]
    labels = LABELS[locale]
    shown = content["items"][:MAX_LISTED_ITEMS]
    items = [
        {**line, "url": _tracked_link(log, line["path"], "product", locale)}
        for line in shown
    ]
    context = {
        "lang": locale,
        "labels": labels,
        "subject": labels["subject"][log.step],
        "items": items,
        "more_text": (
            labels["more_items"].format(count=len(content["items"]) - len(shown))
            if len(content["items"]) > len(shown) else ""
        ),
        "total_text": content["total_text"],
        "prices_note": labels["prices_note"].format(date=timezone.localdate().strftime("%d.%m.%Y")),
        "checkout_url": _tracked_link(log, "/checkout", "checkout", locale),
        "cart_url": _tracked_link(log, "/cart", "cart", locale),
        "manager_url": _manager_url(),
        "unsubscribe_url": unsubscribe_url(user, locale),
        "profile_url": f"{site_url()}{_localized_path('/profile', locale)}",
    }
    html_body = render_to_string("emails/cart_reminder.html", context)
    text_lines = [context["subject"], "", labels["intro"], ""]
    for line in items:
        text_lines.append(f"• {line['name']} — {line['quantity']} × {line['price_text']}: {line['url']}")
    if context["more_text"]:
        text_lines.append(context["more_text"])
    text_lines += [
        "",
        f"{labels['total']}: {content['total_text']}",
        context["prices_note"],
        "",
        labels["next_step"],
        f"{labels['cta_checkout']}: {context['checkout_url']}",
        f"{labels['cta_cart']}: {context['cart_url']}",
    ]
    if context["manager_url"]:
        text_lines.append(f"{labels['cta_manager']}: {context['manager_url']}")
    text_lines += ["", labels["reason"], f"{labels['unsubscribe']}: {context['unsubscribe_url']}"]
    return context["subject"], "\n".join(text_lines), html_body


def render_telegram(content: dict, log: CartReminderLog) -> tuple[str, dict]:
    """(текст с HTML-разметкой Telegram, reply_markup с кнопками)."""
    locale = content["locale"]
    labels = LABELS[locale]
    esc = html.escape
    shown = content["items"][:MAX_LISTED_ITEMS]
    lines = [f"🛒 <b>{esc(labels['subject'][log.step])}</b>", esc(labels["intro"]), ""]
    for line in shown:
        url = _tracked_link(log, line["path"], "product", locale)
        lines.append(
            f"• <a href=\"{esc(url, quote=True)}\">{esc(line['name'])}</a> — "
            f"{line['quantity']} × {esc(line['price_text'])}"
        )
    if len(content["items"]) > len(shown):
        lines.append(esc(labels["more_items"].format(count=len(content["items"]) - len(shown))))
    lines += [
        "",
        f"<b>{esc(labels['total'])}: {esc(content['total_text'])}</b>",
        esc(labels["prices_note"].format(date=timezone.localdate().strftime("%d.%m.%Y"))),
        "",
        esc(labels["next_step"]),
        "",
        esc(labels["tg_stop_hint"]),
    ]
    keyboard = [
        [{"text": labels["cta_checkout"], "url": _tracked_link(log, "/checkout", "checkout", locale)}],
        [{"text": labels["cta_cart"], "url": _tracked_link(log, "/cart", "cart", locale)}],
    ]
    manager = _manager_url()
    if manager:
        keyboard.append([{"text": labels["cta_manager"], "url": manager}])
    keyboard.append([{"text": labels["tg_stop"], "callback_data": CART_REMINDERS_OFF_CALLBACK}])
    return "\n".join(lines), {"inline_keyboard": keyboard}


def _send_email(user, recipient: str, content: dict, log: CartReminderLog) -> str:
    """Пустая строка — отправлено, иначе текст ошибки."""
    from .tasks import _send_email_with_ipv4_fallback

    subject, text_body, html_body = render_email(user, content, log)
    one_click = unsubscribe_url(user, content["locale"])
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@mudaroba.local"),
        to=[recipient],
        headers={
            "List-Unsubscribe": f"<{one_click}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )
    message.attach_alternative(html_body, "text/html")
    try:
        _send_email_with_ipv4_fallback(message)
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return ""


def _send_telegram(chat_id: str, content: dict, log: CartReminderLog) -> str:
    text, markup = render_telegram(content, log)
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "reply_markup": markup,
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        # Текст исключения может содержать адрес с токеном бота
        return type(exc).__name__
    if not resp.ok:
        return f"HTTP {resp.status_code}: {resp.text[:200]}"
    return ""


def send_reminder(user, step: int, conf: CartReminderSettings | None, *, cart=None, items=None, currency=None, locale=None) -> list[CartReminderLog]:
    """Отправляет одно напоминание во все доступные каналы клиента; каждая попытка — строка журнала.

    conf=None — тестовая отправка администратору: каналы не зависят от настроек и подтверждения email.
    """
    if items is None:
        items = _cart_items(cart)
    if not items:
        return []
    locale = normalize_locale(locale or getattr(cart, "locale", ""))
    content = build_reminder_content(user, items, currency or getattr(cart, "currency", "RUB"), locale)
    is_test = conf is None

    logs = []
    email = (user.email or "").strip()
    email_ok = (
        (is_test and email and not email.lower().endswith(PLACEHOLDER_EMAIL_SUFFIX))
        or (not is_test and conf.email_enabled and has_confirmed_email(user))
    )
    if email_ok:
        log = _new_log(user, cart, step, CartReminderLog.Channel.EMAIL, email, content)
        _finish_log(log, _send_email(user, email, content, log))
        logs.append(log)

    telegram_ok = (is_test or conf.telegram_enabled) and has_telegram(user)
    if telegram_ok:
        chat_id = str(user.telegram_id).strip()
        recipient = f"@{user.telegram_username}" if user.telegram_username else chat_id
        log = _new_log(user, cart, step, CartReminderLog.Channel.TELEGRAM, recipient, content)
        _finish_log(log, _send_telegram(chat_id, content, log))
        logs.append(log)
    return logs


def send_test_reminder(user, locale: str = "ru") -> list[CartReminderLog]:
    """«Отправить тестовое мне»: свой Список заявки администратора, а если он пуст — 3 свежих товара."""
    from apps.catalog.models import Product

    cart = Cart.objects.filter(user=user).first()
    items = _cart_items(cart) if cart else []
    currency = cart.currency if cart else ("USD" if normalize_locale(locale) == "en" else "RUB")
    if not items:
        cart = None
        products = Product.objects.filter(is_active=True, price__isnull=False, price__gt=0).order_by("-updated_at")[:3]
        items = [
            CartItem(product=product, quantity=1, price=product.price, currency=product.currency or "RUB")
            for product in products
        ]
    return send_reminder(user, CartReminderLog.Step.TEST, None, cart=cart, items=items, currency=currency, locale=locale)
