# PharmaTurk Mobile App

Flutter мобильное приложение для интернет-магазина PharmaTurk (Turk Export).

## Последние обновления

- **Поиск по тексту** — полнотекстовый поиск товаров с debounce
- **Поиск по фото** — загрузка изображения или вставка URL для визуального поиска похожих товаров (RecSys)
- **Локализация** — русский и английский интерфейс (ru/en)
- **Избранное** — исправлена работа с API и отображение

## Структура проекта

```
lib/
├── models/          # Модели данных
│   ├── product.dart
│   ├── cart.dart
│   ├── order.dart
│   ├── user.dart
│   ├── favorite.dart
│   ├── banner.dart
│   ├── testimonial.dart
│   └── models.dart
├── services/        # API сервисы
│   ├── api_client.dart
│   ├── auth_service.dart
│   ├── catalog_service.dart
│   ├── cart_service.dart
│   ├── order_service.dart
│   ├── favorite_service.dart
│   ├── testimonial_service.dart
│   └── services.dart
├── providers/       # State management
│   ├── auth_provider.dart
│   ├── cart_provider.dart
│   ├── catalog_provider.dart
│   ├── favorite_provider.dart
│   ├── locale_provider.dart
│   ├── order_provider.dart
│   └── providers.dart
├── screens/         # UI экраны
│   ├── main_screen.dart
│   ├── home_screen.dart
│   ├── catalog_screen.dart
│   ├── product_detail_screen.dart
│   ├── search_screen.dart
│   ├── visual_search_screen.dart
│   ├── cart_screen.dart
│   ├── checkout_screen.dart
│   ├── order_success_screen.dart
│   ├── orders_screen.dart
│   ├── order_detail_screen.dart
│   ├── profile_screen.dart
│   ├── login_screen.dart
│   ├── register_screen.dart
│   ├── favorites_screen.dart
│   ├── addresses_screen.dart
│   ├── settings_screen.dart
│   └── screens.dart
├── l10n/            # Локализация
│   └── app_localizations.dart
├── utils/           # Утилиты
│   ├── image_url.dart
│   └── price_format.dart
└── main.dart
```

## Установка

1. Убедитесь, что у вас установлен Flutter SDK (версия 3.0.0 или выше)

2. Перейдите в папку mobile:
```bash
cd mobile
```

3. Установите зависимости:
```bash
flutter pub get
```

4. Сгенерируйте код для JSON сериализации:
```bash
dart run build_runner build --delete-conflicting-outputs
```

5. URL API задаётся через `--dart-define=API_BASE_URL=...` при запуске и сборке (см. [COMMANDS.md](COMMANDS.md))

## Запуск

Подробная шпаргалка команд — [COMMANDS.md](COMMANDS.md).

### Разработка (Web)
```bash
flutter run -d chrome --web-browser-flag "--disable-web-security" --dart-define=API_BASE_URL=http://localhost:8000
```

### Продакшн сборка

**Web:**
```bash
flutter build web --dart-define=API_BASE_URL=https://api.pharmaturk.com
```

**Android:**
```bash
flutter build apk --dart-define=API_BASE_URL=https://api.pharmaturk.com
```

**iOS:**
```bash
flutter build ios --release --dart-define=API_BASE_URL=https://api.pharmaturk.com
```

## Функциональность

### Авторизация
- Регистрация нового пользователя
- Вход по email и паролю
- Социальная авторизация (Google, Telegram)
- Восстановление пароля
- Подтверждение email

### Каталог
- Просмотр категорий товаров
- Фильтрация по брендам, цене, наличию
- **Поиск по тексту** — с главной и из каталога
- **Поиск по фото** — загрузка изображения (галерея/камера) или вставка URL
- Просмотр деталей товара
- Похожие товары

### Корзина
- Добавление/удаление товаров
- Изменение количества
- Применение промокодов
- Просмотр итоговой суммы

### Оформление заказа
- Заполнение контактных данных
- Выбор способа оплаты
- Выбор адреса доставки
- Подтверждение заказа

### Профиль
- Просмотр и редактирование профиля
- История заказов
- Избранные товары
- Управление адресами доставки
- Настройки приложения (язык ru/en, валюта)

## API Endpoints

Приложение использует следующие API endpoints:

### Каталог
- `GET /api/catalog/products/` - Список товаров
- `GET /api/catalog/products/search?q=` - Поиск по тексту
- `GET /api/catalog/products/{slug}/` - Детали товара
- `GET /api/catalog/categories/` - Список категорий
- `GET /api/catalog/brands/` - Список брендов
- `GET /api/catalog/banners/` - Баннеры

### Поиск по фото (RecSys)
- `POST /api/upload/temp/` - Загрузка временного изображения
- `POST /api/recommendations/search_by_image/` - Поиск похожих товаров по изображению

### Корзина
- `GET /api/orders/cart/` - Получить корзину
- `POST /api/orders/cart/add/` - Добавить в корзину
- `POST /api/orders/cart/{id}/update/` - Обновить количество
- `DELETE /api/orders/cart/{id}/remove/` - Удалить из корзины
- `POST /api/orders/cart/clear/` - Очистить корзину
- `POST /api/orders/cart/apply-promo/` - Применить промокод

### Заказы
- `GET /api/orders/orders/` - Список заказов
- `GET /api/orders/orders/{id}/` - Детали заказа
- `POST /api/orders/orders/create-from-cart/` - Создать заказ

### Пользователи
- `POST /api/users/login/` - Вход
- `POST /api/users/register/` - Регистрация
- `POST /api/users/logout/` - Выход
- `GET /api/users/profile/me/` - Профиль
- `GET /api/users/addresses/` - Адреса

### Избранное
- `GET /api/catalog/favorites/` - Список избранного
- `POST /api/catalog/favorites/add/` - Добавить в избранное
- `DELETE /api/catalog/favorites/remove/` - Удалить из избранного

## Устранение неполадок

### DioException: connection error / XMLHttpRequest onError (Flutter Web)

При оплате корзины в браузере может возникать ошибка соединения. Возможные причины:

1. **CORS** — бэкенд должен разрешать запросы с origin Flutter (например, `http://localhost:XXXXX`). Убедитесь, что в `backend/config/settings.py` при `DEBUG=True` установлено `CORS_ALLOW_ALL_ORIGINS = True`.

2. **Бэкенд не запущен** — проверьте, что Django-сервер доступен по `API_BASE_URL` (по умолчанию `http://localhost:8000`).

3. **Временный обход CORS для разработки** — запуск Chrome с отключённой проверкой безопасности:
   ```bash
   flutter run -d chrome --web-browser-flag "--disable-web-security" --dart-define=API_BASE_URL=http://localhost:8000
   ```

4. **Проверка API** — откройте в браузере `http://localhost:8000/api/docs/` и проверьте `POST /api/orders/orders/create-from-cart/` в Swagger.

### Assertion failed: PointerDeviceKind.trackpad (Flutter Web)

Известная ошибка Flutter Web при скролле тачпадом в Chrome (`!identical(kind, PointerDeviceKind.trackpad)`). Варианты решения:

1. **Обновить Flutter** — `flutter upgrade` (в новых версиях может быть исправлено).
2. **Использовать мышь** вместо тачпада при тестировании в браузере.
3. **Запуск с HTML-рендерером** — `flutter run -d chrome --web-renderer html` (иногда помогает).

### Ошибки сборки / странное поведение

Выполните полную пересборку:
```bash
flutter clean && flutter pub get && dart run build_runner build --delete-conflicting-outputs
```
Подробнее — [COMMANDS.md](COMMANDS.md).

## Зависимости

- `provider` - State management
- `dio` - HTTP клиент
- `json_annotation` + `json_serializable` - JSON сериализация
- `cached_network_image` - Загрузка и кэширование изображений
- `shared_preferences` - Локальное хранилище
- `intl` - Интернационализация
- `url_launcher` - Открытие ссылок
- `share_plus` - Поделиться
- `image_picker` - Выбор фото из галереи и камеры (поиск по фото)

## Лицензия

MIT License
