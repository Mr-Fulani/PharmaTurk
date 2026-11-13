# Content-Security-Policy и токены входа

Актуально: **13 ноября 2026 года** (TD-018, TD-033). CSP переведена в enforce; следующий шаг — nonce
вместо `'unsafe-inline'`.

## Что сейчас работает

### CSP в режиме enforce

- Заголовок `Content-Security-Policy` отдаёт Next.js для всех страниц
  (`frontend/next.config.js`, `buildCsp`, константа `CSP_ENFORCE`). Только production-сборка:
  `next dev` нужен `eval` и HMR-сокеты.
- Браузер **блокирует** всё, что политика не разрешает: нарушение видно в консоли
  («Refused to load…») и уходит на `POST /api/csp-report/`.
- **Откат на Report-Only** (ничего не блокировать, только отчёты): в `frontend/next.config.js`
  поставить `const CSP_ENFORCE = false` и выкатить frontend. Заголовок запекается в сборку
  (`routes-manifest.json`), поэтому без пересборки образа frontend откат не действует.
  Аварийно, без новой сборки — `scripts/release/rollback.sh` на прошлый выпуск (до 13.11.2026 он
  Report-Only), но так откатится и всё остальное из выпуска.
- `/api/csp-report/` (`api/views.py`, `CspReportView`) пишет в лог backend строку
  `CSP violation: <директива> blocked <источник> on <страница>` (логгер `csp`, без
  query-строк — там бывают персональные данные). Лимит — 20/мин и 300/сутки на IP.
- С 13.11.2026 отчёты хранятся и в базе — таблица `CspViolation` (`apps/monitoring`, с User-Agent, без IP),
  30 дней (ночная задача `prune_csp_violations`): лог контейнера пропадает при каждом выпуске, 13.11
  так потерялись отчёты за 9 часов. Сводка:
  `docker exec mudaroba-backend-1 /app/.venv/bin/python manage.py csp_violations --hours 24` —
  директива, источник, раздел сайта и устройство (iPhone, Android, Windows, Mac).
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
| Видео товаров у источника | media | `www.ikea.com` (мебель IKEA), `umma-land.com` (книги) |
| Встроенные видео | frame | `www.youtube.com`, `www.youtube-nocookie.com`, `player.vimeo.com` |
| Шрифт страницы 404 | style/font | `fonts.googleapis.com`, `fonts.gstatic.com` |
| Картинки | img | любой `https:` — фото товаров приходят с доменов источников |

Ссылки WhatsApp/Telegram/VK (`wa.me`, `t.me`, `window.open`) — переходы, CSP их не
ограничивает. `object-src 'none'`, `base-uri 'self'`, `frame-ancestors 'none'`.

На страницах входа дополнительно разрешён `'unsafe-eval'`: виджет Telegram выполняет
`data-onauth` через `eval`. На остальных страницах его нет. CSP берётся из документа, а не
из адреса: после перехода на `/auth` внутри сайта (ссылка «Войти», `router.push`) действует
политика прежней страницы, без `'unsafe-eval'`. Поэтому виджет Telegram в production
перезагружает страницу, если документ открыт не на `/auth`.

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
- 25.10.2026, релиз 066fa91: отчётов VK ID больше нет. Первые отчёты посетителя с согласием —
  Метрика: `script-src` `https://mc.yandex.com/metrika/tag_phono.js`, `frame-src`
  `https://mc.yandex.com`, `script-src` `https://<случайное имя>.ru/wsync/…` (синхронизация
  Метрики со случайного домена — в список не внести). До enforce: добавить `mc.yandex.com` в
  `script-src`/`frame-src`; потерю `wsync` принять (на счётчик не влияет) или оставить Метрику
  без enforce.

- 30–31.10.2026, релиз c5ac8ac, отчёты за 31 час (лог живёт до пересоздания контейнера): eval виджета
  Telegram на `/auth` и `/en/auth` — 510, `mc.yandex.com` и `mc.yandex.ru` — 43, `wsync` Метрики — 9,
  стили переводчика браузера `www.gstatic.com` — 3. На остальных страницах нарушений нет. Политика
  дополнена: `'unsafe-eval'` только на страницах входа (правило `/auth/:path*` в `next.config.js`,
  с локалями), Метрика, `www.gstatic.com`. `wsync` не разрешаем.

- 02–03.11.2026, релиз 76cd1e6d, отчёты за 10 часов: eval на `/auth` — 2 (вход после перехода
  внутри сайта: `/profile` → `router.replace('/auth')`, политика прежней страницы — после enforce
  вход через Telegram сломался бы; исправлено перезагрузкой, см. выше), `media-src`
  `www.ikea.com/pvid/…mp4` на `/brand/ikea` — 1 (видео 678 товаров IKEA и книг umma-land
  открываются с сайта источника; добавлены в `media-src`).

## Проверка перед enforce 13.11.2026 (выпуск dace35bb)

Ручной проход во встроенном браузере с принятыми cookie (GA4 и Метрика загружены), нарушения
собирались `ReportingObserver` с `buffered: true`; контрольное нарушение (`object-src`) поймалось, т. е.
способ работает. Три темы (`?skin=iznik|green|cream`), RU и EN:

- главная с видео-баннерами `cdn.mudaroba.com`, шрифты тем (`/fonts/Onest-v1.woff2` и др.),
  инлайн-скрипт `#theme-catch-up` (запрос `/api/settings/appearance` — свой домен);
- разделы (лекарства, обувь, услуги), бренд IKEA, карточка лекарства и обуви, `/drugs/<slug>`;
- поиск по слову и по фото (загрузка в `/api/upload/temp/`);
- «Список заявки» с товаром и оформление заявки (без отправки);
- `/auth` и `/en/auth` (виджеты Telegram и Google), переход «Войти» внутри сайта (страница
  перезагружается, нарушения `eval` нет), `/profile` без входа (уводит на `/auth`);
- блог и статья, «Как заказать», доставка, доставка по Стамбулу, `/turetskaya-apteka`, отзывы, 404.

Нарушений нет ни на одной странице. Не проверено: профиль с входом (нужен вход в аккаунт) и сам вход
через Telegram/Google до конца. Лог отчётов на проде за 12–13.11 из этой сессии не разобран (нет
доступа к серверу) — смотреть командой из шага 1 ниже.

## Первый день enforce 13.11.2026 (выпуск 86cca35c, 07:13 МСК)

- Ручная проверка после выкатки (главная, `/auth`, бренд IKEA, мобильный размер — главная и карточка):
  GA4, Метрика, видео баннеров, виджеты Telegram и Google работают, нарушений нет.
- Лог backend за 07:13–16:11 потерян выпуском 4ddd8f86. По логу nginx за это время — 7 запросов на
  `/api/csp-report/`, все с iPhone (Safari и Chrome iOS): 4 с главной, 3 с карточек лекарств из Google.
  Содержимое не сохранилось. Фон до enforce тот же: 12.11 — 16 отчётов, из них 10 с iPhone, с тех же
  страниц; единственный разобранный отчёт с iPhone (13.11 05:30) — `wsync` Метрики. Вероятно, это
  синхронизация cookie Метрики в Safari (ITP), её мы не разрешаем. Проверить по таблице `CspViolation`.

## Как перейти в enforce (TD-033)

1. **Неделя наблюдения.** После релиза смотреть сводку `manage.py csp_violations --hours 24` (см. выше;
   до 13.11.2026 — только лог: `docker logs --since 24h mudaroba-backend-1 2>&1 | grep -o 'CSP violation: [^"]*' | sort | uniq -c | sort -rn | head -50`).
   Каждый повторяющийся источник: либо свой (добавить в `CSP_REPORT_ONLY`), либо
   мусор расширений браузера (`chrome-extension:`, `moz-extension:`, `safari-web-extension:` —
   игнорировать), либо реальная проблема.
2. **Ручная проверка без нарушений** в консоли браузера (RU и EN): главная с
   видео-баннерами, категория, карточка товара (фото, видео, YouTube), корзина,
   оформление заявки, вход через Telegram и Google, страница 404, «Как заказать».
   Повторить с принятыми cookie (грузятся GA4 и Метрика).
3. **Enforce** — сделано 13.11.2026: `CSP_ENFORCE = true` в `next.config.js` (оба правила, общее и
   `/auth/:path*`, политика прежняя, `report-uri` остался), тест `src/lib/securityHeaders.test.mjs`.
   После выкатки — сутки смотреть лог (шаг 1): теперь каждая строка — реально заблокированный
   ресурс. Если ломается что-то у посетителей — откат (`CSP_ENFORCE = false`, см. выше) и разбор.
4. **Ужесточение после enforce** — отдельными релизами, каждый снова через
   Report-Only на неделю (вторым заголовком `Content-Security-Policy-Report-Only` с более строгой
   политикой рядом с действующей):
   - nonce вместо `'unsafe-inline'` в `script-src`: nonce генерируется на каждый запрос в
     `middleware`, передаётся в `_document` и ставится на все инлайн-скрипты — Consent Mode
     (`gtm-consent-default`), `#theme-catch-up`, инициализацию gtag и Метрики (`next/script`),
     `__NEXT_DATA__`. Заголовок тогда задаёт `middleware`, а не `headers()` в `next.config.js`;
     страницы с nonce не кэшируются Cloudflare целиком (`s-maxage`) — проверить, не теряем ли кэш;
   - сужение `img-src`;
   - перевод access-токена из JS-cookie.

## Проверка на проде

```bash
curl -sI https://mudaroba.com/ | grep -i '^content-security-policy'
```

В DevTools → Console на страницах сайта не должно быть строк «Refused to …» для
своих ресурсов и сервисов из таблицы выше.
