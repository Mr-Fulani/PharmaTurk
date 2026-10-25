# Аналитика: согласие, события и цели

## Счётчики

| Система | ID | Где задан |
|---|---|---|
| GA4, ресурс **Mudaroba** (до 17.10.2026 — turk-export), поток «Mudaroba», аккаунт Google Mr.Fulani | `G-C333XNVW4X` | `NEXT_PUBLIC_GA4_ID` |
| Яндекс Метрика | `108408259` | `NEXT_PUBLIC_YM_ID` |
| GTM | `GTM-MR4C4W83` — пустой, на сайте не грузится | `NEXT_PUBLIC_GTM_ID` (не используется) |

| Яндекс.Вебмастер, подтверждение прав (мета-тег `yandex-verification` в `_document.tsx`) | `f77544b8feb6573b` | `NEXT_PUBLIC_YANDEX_VERIFICATION` |

Переменные `NEXT_PUBLIC_*` вшиваются в сборку фронтенда: смена ID = пересборка образа. Образы для прода
собирает CI, поэтому значения берутся из **переменных репозитория GitHub** (Settings → Variables), а не из
`.env` сервера; новая переменная добавляется в `ci.yml`, `docker-compose.yml` (build args) и `frontend/Dockerfile`.
25.10.2026 тег Вебмастера пропал именно так: переменная была только в `.env` сервера, и Яндекс снял права.

## Согласие на cookie

- Статус хранится в cookie `pharma_cookie_consent` (`accepted` / `rejected`).
- `hooks/useCookieConsent.ts` — общее состояние для всех компонентов
  (`useSyncExternalStore`): после «Принять» `_app.tsx` сразу грузит Метрику и GA4,
  без перезагрузки.
- **До согласия ни gtag.js, ни Метрика не загружаются** — события копятся только в локальном
  `dataLayer` и никуда не уходят. Поэтому все отчёты (и посещения, и конверсии) — только по
  согласившимся; доля конверсий от этого не искажается.
- gtm.js не загружается (с 17.10.2026): контейнер пуст, а 116 КБ скрипта на
  каждой странице отнимали полосу у LCP. В `_document.tsx` при заданном GA4 остаётся
  Consent Mode `default`: `denied` до ответа, `granted` при сохранённом согласии;
  gtag.js подхватывает его из `dataLayer`. При принятии — `consent update granted` +
  событие `cookie_consent_granted` (`lib/gtm.ts`). Если в GTM появятся теги — вернуть
  загрузку контейнера в `_document.tsx` и убрать дублирование событий в gtag (ниже).
- Метрика инициализируется без `defer`, поэтому первый просмотр учитывается при
  init; дальше — `ymPageHit` на `routeChangeComplete`. Опции счётчика: `clickmap`, `trackLinks`,
  `accurateTrackBounce`, `ecommerce: 'dataLayer'`; Вебвизор выключен (`webvisor: false`, скорость).

## Просмотры страниц

- GA4: первый просмотр — `config` в `_app.tsx`, переходы внутри сайта GA4 считает сам —
  расширенная статистика потока, «Изменения страницы на основе событий в истории браузера»
  (включено, проверено по конфигу gtag 20.10.2026). **Не выключать**, иначе переходы перестанут
  считаться. Ручной `gtag('config', …, {page_path})` на каждый переход (до 20.10.2026) задваивал
  просмотры — удалён.
- Метрика: `ymPageHit` на `routeChangeComplete`.

## События

Компоненты вызывают только хелперы `lib/gtm.ts`: событие уходит в `dataLayer`
(оттуда e-commerce читает Метрика), дублируется в GA4 через `gtag('event', …)`
(`ga4EventParams` поднимает ecommerce-поля на верхний уровень) и, где указано, отмечает цель Метрики.

| Событие GA4 | Где | Данные | Цель Метрики |
|---|---|---|---|
| `view_item_list` | категория (`categories/[slug].tsx`), бренд (`brand/[slug].tsx`) — хук `useViewItemList`, повтор того же списка не шлётся | item_list_id `category:<slug>` / `brand:<slug>`, item_list_name, items (item_id, название, тип, index) | — (e-commerce из dataLayer) |
| `view_item` | карточка товара, один раз на товар | item_id, название, тип (`item_category`), бренд, цена, валюта карточки | — (e-commerce из dataLayer) |
| `add_to_cart` («В заявку») | `AddToCartButton`, `BuyNowButton` | та же позиция, что во view_item + размер (`item_variant`), quantity, value = цена × кол-во | `add_to_cart` / `buy_now` |
| `add_to_wishlist` | `store/favorites.ts` после успешного добавления (все кнопки избранного) | item_id, название, тип, цена, валюта | `add_to_wishlist` |
| `begin_checkout` | `checkout.tsx`, после загрузки непустой корзины | позиции, сумма, валюта корзины | `begin_checkout` |
| `generate_lead` | заявка из корзины (`checkout.tsx`, после создания заказа) | `lead_source=order`, value, currency, transaction_id = номер заявки, payment_method | `generate_lead` + `order_request` (доход по цели: `order_price`, `currency`) |
| `generate_lead` | заявка на подбор `SourcingRequestForm` | `lead_source=sourcing`, placement: home / category / search / how_to_order | `generate_lead` + `sourcing_request` |
| `search` | `search.tsx` | search_term | `search` (параметр `query`) |
| `contact_click` | любая ссылка WhatsApp / Telegram / телефон / email / VK на сайте — общий обработчик `handleContactLinkClick` в `_app.tsx` | contact_channel; placement: `widget` (плавающий виджет), `footer`, иначе `page` (страницу даёт page_location) | `click_whatsapp`, `click_telegram`, `click_phone`, `click_email`, `click_vk` (параметр `placement`) |

- **Заявка — лид, а не покупка.** Онлайн-оплаты нет, заказ = заявка менеджеру, поэтому
  `purchase` с выручкой больше не шлётся (до 20.10.2026 слался и раздувал «доход» в GA4).
  Если онлайн-оплата вернётся — `purchase` слать по факту оплаты, не при создании заявки.
- Событие `sourcing_request` в GA4 (до 20.10.2026) заменено на `generate_lead` с `lead_source=sourcing`.
- Контактные ссылки распознаёт `contactChannelFromHref`; ссылки «поделиться» (`wa.me/?text=`,
  `t.me/share`, `vk.com/share.php`) и контакты пользователей на `/profile`, `/user/…` не считаются.
  Новый блок с контактами — добавить контейнеру `data-analytics-placement="<имя>"`.
- Пол, возраст, интересы и география не собираются кодом и не кладутся в события: GA4 берёт
  их из Google Signals (агрегированно), Метрика — сама. Персональные данные (имя, телефон,
  email, текст заявки) в события не передавать.
- GA4 сам добавляет события расширенной статистики: `view_search_results` (параметр `q`),
  `form_start`/`form_submit`, `click` (исходящие ссылки), `scroll`, `file_download`.

## UTM напоминаний о Списке заявки

Ссылки из напоминаний ([CART_REMINDERS.md](CART_REMINDERS.md)) приходят на сайт с метками —
в GA4 «Источник / канал» и в Метрике «UTM-метки»:

| Метка | Значения |
|---|---|
| `utm_source` | `cart_reminder` |
| `utm_medium` | `email` / `telegram` |
| `utm_campaign` | `cart_reminder_1` (первое), `cart_reminder_2` (второе), `cart_reminder_test` (тест из админки) |
| `utm_content` | `product` (карточка товара), `cart` (Список заявки), `checkout` (кнопка «Отправить заявку») |

Заявки после напоминаний видны в отчётах по `generate_lead` с этим источником; переходы без
согласия на cookie GA4 не видит, но журнал напоминаний в админке их считает («Перешёл по ссылке»).

## Серверные события (Measurement Protocol) — не используются

Рассматривались для заявок (отправка `generate_lead` из Django при создании заявки).
Не внедрено (20.10.2026): по согласившимся браузерное событие уже надёжно (после заявки
страница живёт ещё секунды, gtag шлёт через sendBeacon), а слать за несогласившихся нельзя
по закону и нельзя по смыслу — их посещений в GA4 нет, конверсия завысится. Полный список
заявок — в админке Django (источник правды по количеству). Вернуться, если появится
онлайн-оплата (подтверждение оплаты приходит на сервер) или выгрузка офлайн-конверсий в рекламу.

## Настройки в интерфейсах (делает владелец)

GA4 (Администратор → ресурс Mudaroba):
- Ключевые события: `generate_lead`, `contact_click`.
- Хранение данных → 14 месяцев (по умолчанию 2 — исследования воронок дальше не видят).
- Сбор данных → Google Signals включить; демография появится в отчётах «Пользователи»
  при достаточном трафике (пороги GA4).
- Расширенная статистика потока не выключать (см. «Просмотры страниц»).

Метрика (счётчик 108408259 → Настройки):
- Электронная коммерция — включить (контейнер `dataLayer`).
- Цели «JavaScript-событие»: `generate_lead`, `order_request`, `sourcing_request`,
  `add_to_cart`, `buy_now`, `add_to_wishlist`, `begin_checkout`, `search`,
  `click_whatsapp`, `click_telegram`, `click_phone`, `click_email`, `click_vk`.

## Проверка

- Код: `npm test` (`src/lib/gtm.test.mjs` — отправка событий в GA4 и цели Метрики).
- Живой сайт: принять cookie, затем GA4 → Администратор → DebugView (через расширение
  Google Tag Assistant) и отладка Метрики `?_ym_debug=1` (события и цели в консоли).
  GTM-превью не подходит — контейнер не загружается. Формы заявок на проде не отправлять:
  это реальные заявки менеджеру.
