# Content-Security-Policy и токены входа

Актуально: **24 октября 2026 года** (TD-018). Следующий шаг — TD-033.

## Что сейчас работает

### CSP в режиме Report-Only

- Заголовок `Content-Security-Policy-Report-Only` отдаёт Next.js для всех страниц
  (`frontend/next.config.js`, константа `CSP_REPORT_ONLY`). Только production-сборка:
  `next dev` нужен `eval` и HMR-сокеты.
- Браузер **ничего не блокирует**: нарушение видно в консоли («[Report Only] Refused
  to load…») и уходит на `POST /api/csp-report/`.
- `/api/csp-report/` (`api/views.py`, `CspReportView`) пишет в лог backend строку
  `CSP violation: <директива> blocked <источник> on <страница>` (логгер `csp`, без
  query-строк — там бывают персональные данные). Лимит — 20/мин и 300/сутки на IP.
- Django Admin и `/api` эту политику не получают: их отдаёт backend через nginx.

Разрешено политикой:

| Что | Директива | Источники |
|---|---|---|
| GA4 (gtag), Consent Mode | script/connect | `www.googletagmanager.com`, `*.google-analytics.com`, `*.analytics.google.com`, `*.g.doubleclick.net`, `www.google.com` |
| Яндекс Метрика | script/connect | `mc.yandex.ru`, `mc.yandex.com`, `yastatic.net` |
| Вход через Telegram | script/frame/form | `telegram.org`, `oauth.telegram.org` |
| Вход через Google | script/style/frame/connect | `accounts.google.com` |
| Вход через VK ID (`@vkid/sdk`) | frame/connect | `id.vk.ru`, `id.vk.com` |
| Cloudflare (Web Analytics, Turnstile) | script/frame/connect | `static.cloudflareinsights.com`, `cloudflareinsights.com`, `challenges.cloudflare.com` |
| Медиа и видео баннеров | media/connect | свой домен (`/media`, `proxy-media`), `cdn.mudaroba.com`, `blob:` |
| Встроенные видео | frame | `www.youtube.com`, `www.youtube-nocookie.com`, `player.vimeo.com` |
| Шрифт страницы 404 | style/font | `fonts.googleapis.com`, `fonts.gstatic.com` |
| Картинки | img | любой `https:` — фото товаров приходят с доменов источников |

Ссылки WhatsApp/Telegram/VK (`wa.me`, `t.me`, `window.open`) — переходы, CSP их не
ограничивает. `object-src 'none'`, `base-uri 'self'`, `frame-ancestors 'none'`.

Инлайн-скрипты (Consent Mode в `_document.tsx`, инициализация gtag и Метрики в
`_app.tsx`) пока разрешены через `'unsafe-inline'` в `script-src` — это главная
слабость текущей политики, её снимает шаг 3 ниже.

### Токены входа

- Refresh JWT — только в HttpOnly cookie `refresh_token` от backend
  (`apps/users/auth_cookies.py`): `Secure` в проде, `SameSite=Lax`, `Path=/api/auth/`,
  без `Max-Age`. JavaScript её не видит. Подробности — в
  [AUTHENTICATION.md](../backend/apps/users/AUTHENTICATION.md).
- Access JWT (60 мин) — по-прежнему обычная cookie фронта: её читают заголовок
  `Authorization` и SSR корзины/оформления. XSS может унести access, но не долгую
  сессию. Перевод access в память/HttpOnly — отдельная задача (TD-033, шаг 4).

## Проверка на проде 24.10.2026 (релиз 2d5e88f)

- Заголовок `Content-Security-Policy-Report-Only` отдаётся, enforce-заголовка нет.
- Главная, категория, карточка товара, «Заявка» — ни одного отчёта (проверено
  `ReportingObserver` и сетевыми запросами к `/api/csp-report/`; контрольное
  нарушение отправилось и попало в лог, т. е. приёмник работает).
- `/auth` — 4 отчёта:
  - `frame-src`/`connect-src` `https://id.vk.ru` — VK ID не был в политике,
    добавлен (`id.vk.ru`, `id.vk.com`);
  - `script-src eval` из `https://telegram.org/js/telegram-widget.js` — виджет
    выполняет строку `data-onauth="onTelegramAuth(user)"` через `eval`
    (`frontend/src/pages/auth/index.tsx`). **До enforce** выбрать: перевести
    виджет на `data-auth-url` (редирект на свой URL, без `eval`) или разрешить
    `'unsafe-eval'` только для `/auth`. Иначе вход через Telegram сломается.
- Аналитика (GA4, Метрика) грузится только после согласия на cookie — в этой
  проверке согласие не давалось, её отчёты смотреть по логу за неделю.

## Как перейти в enforce (TD-033)

1. **Неделя наблюдения.** После релиза смотреть лог:
   `docker logs --since 24h mudaroba-backend-1 2>&1 | grep -o 'CSP violation: [^"]*' | sort | uniq -c | sort -rn | head -50`.
   Каждый повторяющийся источник: либо свой (добавить в `CSP_REPORT_ONLY`), либо
   мусор расширений браузера (`chrome-extension:`, `moz-extension:`, `safari-web-extension:` —
   игнорировать), либо реальная проблема.
2. **Ручная проверка без нарушений** в консоли браузера (RU и EN): главная с
   видео-баннерами, категория, карточка товара (фото, видео, YouTube), корзина,
   оформление заявки, вход через Telegram и Google, страница 404, «Как заказать».
   Повторить с принятыми cookie (грузятся GA4 и Метрика).
3. **Enforce.** В `next.config.js` сменить ключ заголовка на
   `Content-Security-Policy` (политику оставить прежней, `report-uri` оставить) и
   обновить тест `src/lib/securityHeaders.test.mjs`. Релиз — обычный полный.
   Откат — вернуть `-Report-Only` и выкатить.
4. **Ужесточение после enforce** — отдельными релизами, каждый снова через
   Report-Only на неделю: nonce вместо `'unsafe-inline'` для скриптов (nonce
   генерируется в `middleware` и передаётся в `_document`), сужение `img-src`,
   перевод access-токена из JS-cookie.

## Проверка на проде

```bash
curl -sI https://mudaroba.com/ | grep -i content-security-policy-report-only
```

В DevTools → Console на страницах сайта не должно быть строк `[Report Only]` для
своих ресурсов и сервисов из таблицы выше.
