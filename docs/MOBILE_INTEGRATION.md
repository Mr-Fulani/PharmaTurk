# Руководство по интеграции мобильного приложения PharmaTurk

Flutter-приложение для iOS и Android, работающее с API бэкенда PharmaTurk.

## Быстрый старт

### Требования

- Flutter SDK 3.8+
- Запущенный бэкенд на `http://localhost:8000` (или эмулятор: `http://10.0.2.2:8000`)

### 1. Установка зависимостей

```bash
cd mobile
flutter pub get
dart run build_runner build --delete-conflicting-outputs
```

### 2. Настройка API URL

URL бэкенда задаётся через `--dart-define`:

**Android эмулятор** (10.0.2.2 — хост-машина):

```bash
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

**iOS симулятор**:

```bash
flutter run --dart-define=API_BASE_URL=http://localhost:8000
```

**Production**:

```bash
flutter build apk --release --dart-define=API_BASE_URL=https://api.pharmaturk.com
```

Без `--dart-define` используется fallback: Android — `http://10.0.2.2:8000`, iOS — `http://localhost:8000`.

### 3. Запуск на эмуляторе

```bash
cd mobile
flutter run
```

## Docker

### Web-режим (разработка)

```bash
docker compose --profile mobile up -d backend mobile
```

Приложение будет доступно на http://localhost:8080. API URL внутри Docker: `http://backend:8000`.

**Важно:** На Mac с чипом M1/M2 образ Flutter в Docker может падать с segfault. В этом случае запускайте mobile локально:

```bash
cd mobile
flutter run --dart-define=API_BASE_URL=http://localhost:8000
```

### Сборка APK

```bash
docker compose --profile build run mobile-build
```

APK: `mobile/build/app/outputs/flutter-apk/app-release.apk`

URL API для production задаётся в `.env`:
```bash
MOBILE_API_BASE_URL=https://api.pharmaturk.com
```

## Структура mobile/

```
mobile/
├── lib/
│   ├── constants/       # env.dart — конфигурация API URL
│   ├── models/          # Модели данных (Product, User, Cart и т.д.)
│   ├── providers/       # State management (Provider)
│   ├── screens/         # Экраны приложения
│   ├── services/        # API-клиент и сервисы
│   └── main.dart
├── assets/
│   ├── images/
│   └── icons/
├── pubspec.yaml
└── Dockerfile
```

## API Endpoints (совместимость с бэкендом)

| Endpoint | Описание |
|----------|----------|
| `GET /api/catalog/products/` | Список товаров |
| `GET /api/catalog/products/{slug}/` | Детали товара |
| `GET /api/catalog/products/featured/` | Рекомендуемые товары |
| `GET /api/catalog/products/search/` | Поиск |
| `GET /api/catalog/products/{slug}/similar/` | Похожие товары |
| `GET /api/catalog/categories/` | Категории |
| `GET /api/catalog/brands/` | Бренды |
| `GET /api/catalog/banners/` | Баннеры |
| `GET/POST /api/catalog/favorites/` | Избранное |
| `GET/POST /api/orders/cart/` | Корзина |
| `GET/POST /api/orders/orders/` | Заказы |
| `POST /api/users/login/` | Вход |
| `POST /api/users/register/` | Регистрация |
| `GET /api/users/profile/me/` | Профиль |

## Сборка для production

### Android APK

```bash
cd mobile
flutter build apk --release --dart-define=API_BASE_URL=https://api.pharmaturk.com
```

### iOS

```bash
cd mobile
flutter build ios --release --dart-define=API_BASE_URL=https://api.pharmaturk.com
```

Откройте `ios/Runner.xcworkspace` в Xcode для подписи и публикации.

## Безопасность

- API URL задаётся только через `--dart-define` или fallback для dev.
- Токены не логируются в debug-режиме.
- В production используйте только HTTPS.
