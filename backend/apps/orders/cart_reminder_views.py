"""Публичные ссылки из напоминаний о Списке заявки: отписка и счётчик переходов (docs/CART_REMINDERS.md).

Обычные Django-вьюхи, а не DRF: отдают HTML-страницу и redirect, клиент приходит из письма
без входа. Действие разрешает только подписанный токен из ссылки.
"""
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from apps.users.models import User

from .cart_reminders import normalize_locale, read_unsubscribe_token, resolve_click_token, site_url
from .models import CartReminderLog

UNSUBSCRIBE_LABELS = {
    "ru": {
        "title": "Напоминания о Списке заявки",
        "confirm": "Больше не присылать напоминания о неотправленном Списке заявки — на почту и в Telegram?",
        "button": "Не присылать напоминания",
        "done": "Готово: напоминания отключены. Сообщения о ваших заявках (статус, трек-номер) будут приходить как раньше.",
        "invalid": "Ссылка недействительна. Отключить напоминания можно в профиле на сайте.",
        "profile": "Включить снова можно в профиле",
        "home": "Вернуться на сайт",
    },
    "en": {
        "title": "Request list reminders",
        "confirm": "Stop reminders about your unsent request list — by email and in Telegram?",
        "button": "Stop reminders",
        "done": "Done: reminders are off. Messages about your requests (status, tracking number) will keep coming as before.",
        "invalid": "This link is not valid. You can turn reminders off in your profile on the site.",
        "profile": "You can turn them back on in your profile",
        "home": "Back to the site",
    },
}


def _no_store(response):
    response["Cache-Control"] = "private, no-store"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


@csrf_exempt
@require_http_methods(["GET", "POST"])
def cart_reminder_unsubscribe(request):
    """GET — страница с кнопкой (сканеры ссылок в почте не отписывают клиента сами), POST — отписка.

    POST приходит и от кнопки страницы, и от «отписаться в один клик» почтового клиента
    (List-Unsubscribe-Post, RFC 8058) — токен в обоих случаях в адресе.
    """
    data = read_unsubscribe_token(request.GET.get("t", ""))
    locale = data["locale"] if data else normalize_locale(getattr(request, "LANGUAGE_CODE", ""))
    if data is None:
        state = "invalid"
    elif request.method == "POST":
        User.objects.filter(pk=data["user_id"]).update(cart_reminders_enabled=False)
        state = "done"
    else:
        state = "confirm"
    prefix = "/en" if locale == "en" else ""
    context = {
        "lang": locale,
        "labels": UNSUBSCRIBE_LABELS[locale],
        "state": state,
        "home_url": f"{site_url()}{prefix}/",
        "profile_url": f"{site_url()}{prefix}/profile",
    }
    response = render(
        request,
        "orders/cart_reminder_unsubscribe.html",
        context,
        status=400 if state == "invalid" else 200,
    )
    return _no_store(response)


@require_GET
def cart_reminder_click(request):
    """Переход по ссылке из напоминания: отметка в журнале и redirect на страницу сайта."""
    log_id, path = resolve_click_token(request.GET.get("t", ""))
    if log_id:
        CartReminderLog.objects.filter(pk=log_id, clicked_at__isnull=True).update(clicked_at=timezone.now())
    return _no_store(HttpResponseRedirect(f"{site_url()}{path}"))
