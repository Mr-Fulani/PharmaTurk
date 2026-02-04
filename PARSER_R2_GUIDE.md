# Руководство по парсерам и работе с R2

Документация описывает архитектуру парсинга, взаимодействие с хранилищем Cloudflare R2, настройку учетных данных и процесс добавления новых парсеров.

---

## 1. Общая архитектура

- **Парсеры** живут в `backend/apps/scrapers/parsers/` и возвращают структуру `ScrapedProduct`.
- **Медиа** (фото, видео, гиф) загружаются в R2 через единый слой: `parser_media_handler`.
- **В БД** хранятся только ссылки (URL) на медиа в R2; сами файлы лежат в R2 (или локально, если R2 выключен).
- **Credentials** (логины/пароли для парсинга) хранятся в базе данных в модели `ScraperConfig` и не требуют `.env` файлов.

---

## 2. Свойства парсера: что он должен уметь

### 2.1. Базовый контракт (BaseScraper + ScrapedProduct)

Каждый парсер должен:

1. **Наследоваться от `BaseScraper`** (`backend/apps/scrapers/base/scraper.py`).
2. **Реализовать обязательные методы:**
   - `get_name()` → уникальное имя парсера (например, `"instagram"`, `"ilacabak"`, `"zara"`).
   - `get_supported_domains()` → список доменов.
   - `parse_product_list(category_url, max_pages)` → список `ScrapedProduct`.
   - `parse_product_detail(product_url)` → один `ScrapedProduct` или `None`.
3. **Возвращать данные в `ScrapedProduct`**:
   - `name`, `description`, `url`, `external_id` — идентификация.
   - `images: List[str]` — список URL изображений.
   - `attributes: Dict` — доп. данные (например, `video_url`, `is_video`).

### 2.2. Взаимодействие с R2: только URL медиа

Парсер **не** пишет файлы в R2 сам. Он отдаёт URL медиа. Сохранение выполняет общий сервис `download_and_optimize_parsed_media`.

---

## 3. Загрузка медиа в R2

### 3.1. Единая точка входа

Модуль: `apps.catalog.utils.parser_media_handler`.

```python
from apps.catalog.utils.parser_media_handler import download_and_optimize_parsed_media

# Скачать и сохранить в R2
r2_url = download_and_optimize_parsed_media(
    url=media_url,
    parser_name="instagram",
    product_id=product_data.external_id,
    index=0,
    headers=optional_headers,
)
```

### 3.2. Предотвращение дублирования (Обновлено)

В `apps.catalog.signals` реализована защита от повторного скачивания файлов, уже находящихся в R2.
Система проверяет домены:
- `r2.dev`
- `r2.cloudflarestorage.com`
- Публичный URL R2 из настроек (`R2_PUBLIC_URL`)

Если ссылка ведет на R2, файл **не скачивается заново**, а просто привязывается к товару.

---

## 4. Настройка авторизации парсеров (Новое)

Для парсеров, требующих авторизации (например, Instagram), учетные данные настраиваются через админ-панель.

**Важно:** Не используйте личные аккаунты! Instagram банит за автоматический сбор данных. Используйте специально зарегистрированные бот-аккаунты.

### 4.1. Добавление credentials

1. Зайдите в **Admin Panel > Scrapers > Scraper Configurations**.
2. Выберите конфигурацию (например, "Instagram Parser").
3. В разделе **"Дополнительные настройки" (Additional Settings)** заполните поля:
   - **Логин парсера**: Username бот-аккаунта.
   - **Пароль парсера**: Пароль бот-аккаунта.
4. Сохраните изменения.

### 4.2. Использование в задачах

При запуске задачи через **Instagram Scraper Tasks**:
1. Система автоматически находит активный конфиг парсера Instagram.
2. Извлекает логин/пароль из БД.
3. Передает их в скрипт парсинга.

Переменные окружения (`.env`) для логина/пароля больше не требуются.

---

## 5. Чек-лист для нового парсера

1. **Класс парсера**: Наследовать от `BaseScraper`, реализовать методы.
2. **Регистрация**: Добавить в `backend/apps/scrapers/parsers/registry.py`.
3. **Медиа**: Использовать `download_and_optimize_parsed_media`.
4. **Конфиг**: Создать `ScraperConfig` в админке.

---

## 6. Важные модули

| Задача | Модуль / путь |
|--------|----------------|
| Базовый класс | `backend/apps/scrapers/base/scraper.py` |
| Загрузка в R2 | `backend/apps/catalog/utils/parser_media_handler.py` |
| Настройки R2 | `backend/apps/catalog/utils/storage_paths.py` |
| Сигналы (анти-дубль) | `backend/apps/catalog/signals.py` |
| Модели конфигов | `backend/apps/scrapers/models.py` |
| Админка парсеров | `backend/apps/scrapers/admin.py` |
