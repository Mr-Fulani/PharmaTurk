# Аутентификация и авторизация

Документ описывает фактическую реализацию в `apps/users`, `api/views.py` и
`config/settings.py`.

## Поддерживаемые способы входа

| Способ | Статус | Основной endpoint |
|---|---|---|
| Email + пароль | реализован | `POST /api/users/login/` |
| Username + пароль | реализован | `POST /api/users/login/` |
| Телефон + пароль | реализован | `POST /api/users/login/` |
| Google Identity Services | реализован | `POST /api/users/social-auth/` |
| VK ID | реализован | `POST /api/users/social-auth/` |
| Telegram Login Widget | реализован | `POST /api/users/telegram/login/` |
| SMS-код | заглушка | `/api/users/sms/*` пока не использовать |
| Facebook, Yandex, Apple | не реализованы | провайдеров в `PROVIDERS` нет |

Для парольного входа используется `MultiFieldAuthBackend` из
`apps/users/backends.py`. Он определяет email, username или телефон, нормализует
типовые разделители телефонного номера и затем проверяет пароль и `is_active`.
Поле запроса исторически называется `email`, но принимает любой из трёх видов
логина.

```http
POST /api/users/login/
Content-Type: application/json

{
  "email": "+79991234567",
  "password": "your-password"
}
```

Успешный ответ содержит объект `user` и пару `tokens.access` / `tokens.refresh`.
В защищённых запросах access token передаётся так:

```http
Authorization: Bearer <access-token>
```

Поддерживаемые варианты телефона включают `+79991234567`, `79991234567`,
`+7 999 123 45 67`, `+7-999-123-45-67` и `+7(999)123-45-67`. Поиск по телефону
зависит от согласованного хранения номера; новые номера следует сохранять в
нормализованном международном формате.

## JWT endpoints

Основной frontend использует `/api/users/login/`. Помимо него доступны
стандартные JWT endpoints:

| Endpoint | Тело запроса | Результат |
|---|---|---|
| `POST /api/users/token/` | `username`, `password` | новая пара access/refresh |
| `POST /api/users/token/refresh/` | `refresh` | ротация refresh и новый access |
| `POST /api/users/token/verify/` | `token` | проверка токена |
| `POST /api/auth/jwt/create/` | `username`, `password` | совместимый alias получения пары |
| `POST /api/auth/jwt/refresh/` | `refresh` | совместимый alias обновления |
| `POST /api/users/logout/` | `refresh` + Bearer access | blacklist refresh и деактивация записей `UserSession` |

Поле `username` в JWT endpoint также проходит через `MultiFieldAuthBackend`, то
есть фактически принимает email, username или телефон. Access token живёт 60
минут, refresh token — 7 дней. Refresh-токены ротируются, старый токен после
ротации попадает в blacklist.

## Ограничение частоты запросов

Лимиты считаются по IP, который доверенный nginx записывает в `X-Real-IP`; при
его отсутствии используется `REMOTE_ADDR`. Стандартная конфигурация выбирает
неподделываемый адрес непосредственного peer. Если перед Nginx стоит Cloudflare,
без отдельной trusted real-IP normalization это будет IP edge-узла: безопасно
от spoofing, но несколько клиентов могут делить один throttle bucket. Настройте
реальный IP только на ingress, который проверяет источник proxy-трафика, и
дублируйте критичные лимиты на WAF/edge.

| Группа endpoints | Burst | Sustained |
|---|---:|---:|
| `/api/users/login/`, `social-auth`, `telegram/login`, получение JWT-пары | 5/мин | 50/день |
| регистрация | 3/час | 10/день |
| refresh и verify JWT | 30/мин | 500/день |
| отправка и проверка email-кода | 5/мин | 30/день |

Application-level throttles не заменяют ограничения на доверенном reverse
proxy/WAF, особенно для публичного Telegram webhook.

## Google и VK

`POST /api/users/social-auth/` принимает только реально реализованные провайдеры
`google` и `vk`:

```json
{
  "provider": "google",
  "access_token": "google-id-token"
}
```

Для Google frontend передаёт `credential` от Google Identity Services в поле
`access_token` (историческое имя API-поля). Backend принимает только ID token,
проверяет точное совпадение `aud` с `GOOGLE_CLIENT_ID`, issuer и
`email_verified`. Обычный OAuth access token и fallback через `userinfo` не
поддерживаются. При пустом `GOOGLE_CLIENT_ID` Google-вход отключён fail-closed.

Для VK frontend обменивает `code` через VK ID SDK и отправляет полученный
`access_token`. Backend проверяет токен через VK ID `user_info`, затем при
необходимости использует классический VK API. Не передавайте токены провайдеров
в URL или логи.

Endpoint создаёт пользователя либо находит его по provider ID. Существующий
аккаунт связывается по email только при явном `email_verified=true` от
провайдера. После доказанного владения email пользователь отмечается
подтверждённым, и только тогда к нему могут быть привязаны гостевые заказы с
тем же email. Неподтверждённый или технический `@mudaroba.local` email никогда
не используется для переноса заказов. Поля
`facebook_id`, `yandex_id` и `apple_id` в модели не означают, что эти провайдеры
реализованы.

`SocialAuthView` остаётся публичным для входа, но распознаёт валидный Bearer JWT.
Для уже аутентифицированного пользователя запрос означает явную привязку
provider ID к текущему аккаунту. Подтверждённый provider email может заменить
только технический email либо подтвердить точно совпадающий адрес; конфликт с
email другого аккаунта отклоняется.

## Telegram

Есть два разных сценария:

1. Вход через Telegram Login Widget: виджет отправляет подписанные данные в
   `POST /api/users/telegram/login/`; backend проверяет HMAC и возраст
   `auth_date`, после чего создаёт/находит пользователя и выдаёт JWT.
2. Привязка Telegram к уже вошедшему профилю: JWT-запрос
   `GET /api/users/profile/telegram-bind-link` создаёт одноразовый start token,
   пользователь открывает бота, а сообщение `/start TOKEN` обрабатывает
   `POST /api/users/telegram/webhook/`.

Для обоих сценариев нужны `TELEGRAM_BOT_TOKEN` и имя бота. Webhook публичный и
не использует CSRF, потому что Telegram его не присылает. Он принимает запросы
только с `X-Telegram-Bot-Api-Secret-Token`, совпадающим с
`TELEGRAM_WEBHOOK_SECRET`; команда `set_telegram_webhook` передаёт это же
значение Telegram как `secret_token`. Start token подписан, одноразовый и живёт
15 минут. Публичный endpoint всё равно следует ограничивать на reverse proxy/WAF
и не раскрывать start token в логах.

Production-настройка провайдеров описана в
[`docs/SOCIAL_AUTH_PRODUCTION.md`](../../../docs/SOCIAL_AUTH_PRODUCTION.md).

## Админка Django

`CustomAdminAuthenticationForm` использует тот же multi-field backend, поэтому
поле логина в админке принимает email, username или телефон. Стандартный
`ModelBackend` остаётся fallback в `AUTHENTICATION_BACKENDS`.

## Проверка после изменений

Без запуска инфраструктуры можно проверить настройки и тесты в уже настроенном
окружении:

```bash
cd backend
poetry run python manage.py check
poetry run pytest -q apps/users/test_social_auth_security.py apps/users/tests \
  api/tests/test_auth_throttles.py
```

DB-интеграционные `apps/users/tests.py` запускайте с PostgreSQL test database.
Проверку реального OAuth выполняйте только с тестовыми приложениями провайдеров
и без вывода credentials/tokens в консоль.
