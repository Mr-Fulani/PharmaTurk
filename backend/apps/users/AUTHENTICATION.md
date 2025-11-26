# Система аутентификации

## Поддерживаемые способы входа

### Текущая реализация

1. **Email** - вход по email адресу
2. **Username** - вход по имени пользователя
3. **Телефон** - вход по номеру телефона (поддержка различных форматов)

### Планируемая реализация

4. **Социальные сети**:
   - Google OAuth2
   - Facebook
   - Telegram (через bot API)
   - VK
   - Yandex
   - Apple Sign In

## Как это работает

### Бэкенд аутентификации

Используется кастомный бэкенд `MultiFieldAuthBackend` (`apps/users/backends.py`), который:

1. Определяет тип введенных данных (email, username или телефон)
2. Нормализует данные (например, телефонные номера)
3. Ищет пользователя в базе данных
4. Проверяет пароль

### Админка Django

В админке доступна кастомная форма входа (`CustomAdminAuthenticationForm`), которая:
- Принимает email, username или телефон в одном поле
- Имеет подсказку в placeholder
- Автоматически определяет тип введенных данных

## Примеры использования

### Вход по email
```
Логин: admin@example.com
Пароль: ваш_пароль
```

### Вход по username
```
Логин: admin
Пароль: ваш_пароль
```

### Вход по телефону
```
Логин: +79991234567
Пароль: ваш_пароль
```

Также поддерживаются форматы:
- `79991234567` (без +)
- `+7 999 123 45 67` (с пробелами)
- `+7-999-123-45-67` (с дефисами)
- `+7(999)123-45-67` (со скобками)

## Настройка

Бэкенд настроен в `config/settings.py`:

```python
AUTHENTICATION_BACKENDS = [
    'apps.users.backends.MultiFieldAuthBackend',  # Кастомный бэкенд
    'django.contrib.auth.backends.ModelBackend',  # Стандартный (fallback)
]
```

## Будущая интеграция соцсетей

Структура для интеграции соцсетей подготовлена в:
- `apps/users/social_auth.py` - модуль для будущей реализации
- Модель `User` содержит поля для хранения ID пользователей в соцсетях:
  - `google_id`
  - `facebook_id`
  - `vk_id`
  - `yandex_id`
  - `apple_id`

Для реализации рекомендуется использовать:
- `django-allauth` - комплексное решение для OAuth
- `social-auth-app-django` - альтернативное решение

## API

В REST API также поддерживается вход по email и username через `UserLoginSerializer` (`apps/users/serializers.py`).

Endpoint: `POST /api/users/login/`

Пример запроса:
```json
{
  "email": "admin@example.com",  // или username
  "password": "your_password"
}
```

