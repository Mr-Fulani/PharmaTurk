# Социальная авторизация в production

Актуальный production origin проекта — `https://mudaroba.com`. Если используется
`www`, его нужно настроить отдельно у каждого провайдера и привести к одному
canonical origin редиректом.

В проекте реализованы Google Identity Services, VK ID и Telegram Login Widget.
Facebook, Yandex и Apple пока не имеют backend-провайдеров.

## Общие переменные

Значения берутся из production env. Переменные с префиксом `NEXT_PUBLIC_`
встраиваются в frontend во время `next build`, поэтому после их изменения нужно
пересобрать frontend image, а не только перезапустить контейнер.

```dotenv
SITE_URL=https://mudaroba.com
FRONTEND_SITE_URL=https://mudaroba.com
NEXT_PUBLIC_SITE_URL=https://mudaroba.com

TELEGRAM_BOT_TOKEN=
TELEGRAM_BOT_USERNAME=
TELEGRAM_WEBHOOK_SECRET=
NEXT_PUBLIC_TELEGRAM_BOT_USERNAME=

GOOGLE_CLIENT_ID=
NEXT_PUBLIC_GOOGLE_CLIENT_ID=

VK_APP_ID=
NEXT_PUBLIC_VK_APP_ID=
```

`GOOGLE_CLIENT_ID` должен совпадать с `NEXT_PUBLIC_GOOGLE_CLIENT_ID`, а
`VK_APP_ID` — с `NEXT_PUBLIC_VK_APP_ID`. Backend читает `GOOGLE_CLIENT_SECRET`
и `VK_APP_SECRET`, но текущие GIS/VK ID потоки их не используют. Не публикуйте
секреты под именами `NEXT_PUBLIC_*`.

Также проверьте production CORS/CSRF settings:

```dotenv
DJANGO_ALLOWED_HOSTS=mudaroba.com,www.mudaroba.com
CORS_ALLOWED_ORIGINS=https://mudaroba.com,https://www.mudaroba.com
CSRF_TRUSTED_ORIGINS=https://mudaroba.com,https://www.mudaroba.com
```

Оставляйте `www` только если этот host действительно обслуживается.

## Telegram Login и привязка профиля

### 1. BotFather

В [@BotFather](https://t.me/BotFather) выберите бота и задайте разрешённый
домен `mudaroba.com` без протокола и пути. Username бота без `@` запишите в обе
переменные:

```dotenv
TELEGRAM_BOT_USERNAME=your_bot
NEXT_PUBLIC_TELEGRAM_BOT_USERNAME=your_bot
```

Backend использует первое значение для deep link привязки, frontend — второе
для Login Widget. Для проверки подписи виджета backend обязательно нужен
`TELEGRAM_BOT_TOKEN`.

### 2. Webhook

Публичный URL привязки:

```text
https://mudaroba.com/api/users/telegram/webhook/
```

Сгенерируйте отдельный секрет из разрешённых Telegram символов и сохраните его
в production env, например `openssl rand -hex 32`. Значение не является bot
token и не должно попадать во frontend:

```dotenv
TELEGRAM_WEBHOOK_SECRET=<случайный-секрет-не-короче-32-символов>
```

Обычный старт backend не меняет provider-side webhook. Это защищает
production-бота от случайной перерегистрации при старте staging. После
проверки `SITE_URL` и трёх Telegram-переменных зарегистрируйте webhook
явно в уже запущенном целевом окружении:

```bash
docker compose exec backend poetry run python manage.py set_telegram_webhook
```

Либо без Docker из настроенного backend-окружения:

```bash
cd backend
poetry run python manage.py set_telegram_webhook
```

`REGISTER_TELEGRAM_WEBHOOK_ON_START=1` оставлен как явный operational
override, но в обычном staging/production env должен оставать `0`.

Команда должна вывести именно URL на `mudaroba.com`. Она передаёт
`TELEGRAM_WEBHOOK_SECRET` в Telegram API как `secret_token`; backend сравнивает
тот же секрет с заголовком `X-Telegram-Bot-Api-Secret-Token`. Без секрета или
при недопустимых символах команда завершается ошибкой. Webhook не использует
Django CSRF: Telegram присылает внешний POST. Дополнительно привязка защищена
подписанным одноразовым start token со сроком жизни 15 минут. Ограничьте прямой
доступ к origin и добавьте rate limiting на edge/reverse proxy.

### 3. Проверка

- На `/auth` Telegram widget должен открывать правильного бота.
- Вход через widget должен вернуть профиль и JWT.
- В профиле запрос `GET /api/users/profile/telegram-bind-link` должен вернуть
  `tg://resolve?...&start=...`.
- После `/start TOKEN` поле Telegram должно стать привязанным, а token —
  одноразово погаситься.
- Token, созданный более 15 минут назад, должен отклоняться; запросите новую
  ссылку привязки.

## Google Identity Services

В [Google Cloud Console](https://console.cloud.google.com/) откройте OAuth 2.0
Client ID типа **Web application**.

В **Authorized JavaScript origins** добавьте:

```text
https://mudaroba.com
https://www.mudaroba.com
```

Для текущей кнопки Google Identity Services redirect URI не используется:
frontend получает `credential` через callback и отправляет его в
`POST /api/users/social-auth/`. Если позже появится redirect-based flow,
зарегистрируйте его callback отдельно.

Задайте один и тот же Web Client ID:

```dotenv
GOOGLE_CLIENT_ID=000000000000-example.apps.googleusercontent.com
NEXT_PUBLIC_GOOGLE_CLIENT_ID=000000000000-example.apps.googleusercontent.com
```

Это обязательная production-настройка: backend принимает только Google ID token
и сверяет его `aud` с `GOOGLE_CLIENT_ID` точным совпадением. Обычный OAuth
access token не принимается. Если OAuth consent screen остаётся в testing mode,
добавьте тестовых пользователей; для общего доступа опубликуйте приложение
согласно правилам Google.

Типовые симптомы:

- `no registered origin` — текущий origin отсутствует в Authorized JavaScript
  origins либо frontend собран со старым Client ID;
- `aud не совпадает` — backend и frontend используют разные Client ID;
- кнопка отсутствует — `NEXT_PUBLIC_GOOGLE_CLIENT_ID` не был задан на этапе
  сборки frontend.

## VK ID

В настройках приложения VK ID зарегистрируйте точный redirect URI:

```text
https://mudaroba.com/auth/vk-callback
```

Frontend формирует его как `${window.location.origin}/auth/vk-callback`, поэтому
для `www` нужен отдельный разрешённый URI либо canonical redirect до запуска
авторизации.

Задайте одинаковый ID приложения:

```dotenv
VK_APP_ID=12345678
NEXT_PUBLIC_VK_APP_ID=12345678
```

Frontend через VK ID SDK получает `code`, обменивает его на access token и
отправляет token в `POST /api/users/social-auth/`. Backend проверяет token через
VK ID `user_info`; при сбое использует `users.get` как fallback. Опциональный
`VK_USER_TOKEN` применяется только для обогащения профиля и не должен попадать
во frontend env. В classic fallback `users.get` определяет владельца из самого
access token; переданный frontend `vk_user_id` используется только для сверки,
а не для выбора произвольного профиля.

Типовые симптомы:

- `redirect_uri is incorrect` — URI отличается origin, регистром, протоколом
  или завершающим путём;
- кнопка отсутствует — `NEXT_PUBLIC_VK_APP_ID` не был задан при сборке;
- backend отклоняет token — проверьте, что `VK_APP_ID` соответствует приложению,
  которым token был выпущен.

## Общий smoke-check

1. Убедитесь, что процесс доступен: `GET https://mudaroba.com/api/live/`.
2. Откройте `/auth` в приватном окне: Google/VK должны появляться только при
   заданных public ID; у Telegram проверьте, что поверх иконки действительно
   загрузился кликабельный widget с заданным bot username.
3. Выполните по одному тестовому входу Google, VK и Telegram.
4. Проверьте, что ответ API содержит `tokens.access`, `tokens.refresh` и `user`,
   а защищённый `GET /api/users/profile` работает с Bearer access token.
5. Проверьте логи на ошибки провайдеров, не выводя сами credentials/tokens.

Публичные `social-auth` и `telegram/login` используют login burst/sustained
throttles. Production edge/reverse proxy всё равно должен ограничивать частоту
запросов, особенно к Telegram webhook.
