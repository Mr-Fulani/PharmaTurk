# Шпаргалка: команды для mobile (Flutter)

> Выполнять из папки `mobile/` или `cd mobile` перед запуском.

## Запуск

```bash
# Web (Chrome)
flutter run -d chrome --web-browser-flag "--disable-web-security" --dart-define=API_BASE_URL=http://localhost:8000

# Android (эмулятор)
flutter run -d android --dart-define=API_BASE_URL=http://10.0.2.2:8000

# iOS (симулятор — укажите имя устройства, например "iPhone 15 Plus")
flutter run -d "iPhone 15 Plus" --dart-define=API_BASE_URL=http://localhost:8000
```

## Сборка

```bash
# Web (production)
flutter build web --dart-define=API_BASE_URL=https://api.pharmaturk.com

# Android APK
flutter build apk --dart-define=API_BASE_URL=https://api.pharmaturk.com

# Android App Bundle (для Google Play)
flutter build appbundle --dart-define=API_BASE_URL=https://api.pharmaturk.com
```

## Чистка и пересборка

```bash
# Очистить кэш и билд
flutter clean

# Установить зависимости заново
flutter pub get

# Полная пересборка (после clean)
flutter clean && flutter pub get && flutter run -d chrome --dart-define=API_BASE_URL=http://localhost:8000
```

## Горячие клавиши (во время flutter run)

| Клавиша | Действие |
|---------|----------|
| `r` | Hot reload |
| `R` | Hot restart |
| `q` | Выход |
| `h` | Справка по командам |

## Генерация кода

```bash
# Перегенерировать .g.dart (json_serializable)
dart run build_runner build --delete-conflicting-outputs

# Watch-режим (авто-генерация при изменениях)
dart run build_runner watch --delete-conflicting-outputs
```

## Анализ и линтер

```bash
# Проверка кода
flutter analyze

# Форматирование
dart format .
```

## Тесты

```bash
flutter test
```
