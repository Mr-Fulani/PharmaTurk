# Настройка социальной авторизации на продакшене

## Telegram Login

### Исправление CSRF (403 Forbidden)

В `TelegramAuthView` добавлен `@csrf_exempt`, так как:
- Данные от Telegram Widget проверяются криптографически (HMAC с bot token)
- Виджет не может отправить CSRF-токен Django

### Настройка домена в BotFather

1. Откройте [@BotFather](https://t.me/BotFather) в Telegram
2. Выберите бота: `/mybots` → ваш бот
3. Bot Settings → Domain
4. Укажите домен **без протокола**: `it-dev.space` (или ваш продакшен-домен)

### Переменные окружения

- `TELEGRAM_BOT_TOKEN` — токен бота (обязательно на бэкенде)
- `TELEGRAM_BOT_USERNAME` или `NEXT_PUBLIC_TELEGRAM_BOT_USERNAME` — username бота (например `Turk_ExportBot`). Нужен для привязки Telegram в профиле и для виджета входа.

---

## Google Sign-In

### Ошибки: "no registered origin" и "401: invalid_client"

Нужно настроить приложение в [Google Cloud Console](https://console.cloud.google.com/).

1. **APIs & Services** → **Credentials** → выберите OAuth 2.0 Client ID (тип "Web application")
2. **Authorized JavaScript origins** — добавьте:
   - `https://it-dev.space`
   - `https://www.it-dev.space` (если используется)
3. **Authorized redirect URIs** — для Google One Tap обычно не требуется, но если используете OAuth flow — добавьте callback URL
4. Убедитесь, что Client ID в `NEXT_PUBLIC_GOOGLE_CLIENT_ID` совпадает с ID из консоли
5. Проверьте, что приложение опубликовано (для тестового режима добавьте тестовых пользователей в OAuth consent screen)

### Переменные окружения

- `NEXT_PUBLIC_GOOGLE_CLIENT_ID` — Client ID из Google Cloud Console

---

## VK (ВКонтакте)

### Ошибка: "redirect_uri is incorrect"

Нужно добавить Redirect URI в настройках приложения VK.

1. [Управление приложениями VK](https://vk.com/apps?act=manage)
2. Выберите ваше приложение
3. **Настройки** → **Redirect URI**
4. Добавьте **точно** (с учётом регистра и слешей):
   - `https://it-dev.space/auth/vk-callback`

Формат должен совпадать с тем, что формируется на фронтенде: `${window.location.origin}/auth/vk-callback`.

### Переменные окружения

- `NEXT_PUBLIC_VK_APP_ID` — ID приложения VK

---

## Чеклист для продакшена

| Провайдер | Действие |
|-----------|----------|
| **Telegram** | ✅ CSRF исправлен в коде. Проверить домен в BotFather |
| **Google** | Добавить `https://it-dev.space` в Authorized JavaScript origins |
| **VK** | Добавить `https://it-dev.space/auth/vk-callback` в Redirect URI |
