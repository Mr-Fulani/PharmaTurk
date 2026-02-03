# Руководство по парсерам и работе с R2

Документация описывает, какими свойствами должен обладать парсер в проекте PharmaTurk, как он взаимодействует с хранилищем Cloudflare R2 и как добавлять новые парсеры для разных сайтов.

---

## 1. Общая архитектура

- **Парсеры** живут в `backend/apps/scrapers/parsers/` и возвращают структуру `ScrapedProduct`.
- **Медиа** (фото, видео, гиф) из парсеров загружаются в R2 через единый слой: `parser_media_handler` и динамические пути из `storage_paths`.
- **В БД** для товаров и изображений хранятся только ссылки (URL) на медиа в R2; сами файлы лежат в R2 (или в локальном `default_storage` при отключённом R2).

---

## 2. Свойства парсера: что он должен уметь

### 2.1. Базовый контракт (BaseScraper + ScrapedProduct)

Каждый парсер должен:

1. **Наследоваться от `BaseScraper`** (`backend/apps/scrapers/base/scraper.py`).
2. **Реализовать обязательные методы:**
   - `get_name()` → уникальное имя парсера (например, `"instagram"`, `"ilacabak"`, `"zara"`).
   - `get_supported_domains()` → список доменов, которые парсер обрабатывает.
   - `parse_product_list(category_url, max_pages)` → список `ScrapedProduct`.
   - `parse_product_detail(product_url)` → один `ScrapedProduct` или `None`.
3. **Возвращать данные в формате `ScrapedProduct`** (dataclass):
   - `name`, `description`, `url`, `external_id` — обязательно для идентификации.
   - `images: List[str]` — список URL изображений (первое = главное).
   - `attributes: Dict` — любые доп. данные (например, `video_url`, `is_video` для видео-постов).

Для видео-контента в `attributes` передавайте, например:

- `video_url` — URL видео.
- `is_video` — флаг, что это видео (тогда в каталоге при сохранении заполнится `video_url` у товара, а превью — из `images[0]`).

### 2.2. Взаимодействие с R2: только URL медиа

Парсер **не** должен сам писать файлы в R2. Он должен:

- Отдавать **URL медиа** (картинки, видео, гиф) в полях `ScrapedProduct.images` и при необходимости в `attributes['video_url']`.
- Команда/сервис, которая сохраняет спарсенные товары в БД, вызывает единую функцию загрузки медиа в R2 (см. ниже). После этого в БД попадают уже ссылки на R2.

Итого: парсер отдаёт только ссылки; скачивание и сохранение в R2 выполняет общий слой.

---

## 3. Загрузка медиа в R2 из парсера

### 3.1. Единая точка входа: `download_and_optimize_parsed_media`

Модуль: `apps.catalog.utils.parser_media_handler`.

Использование:

```python
from apps.catalog.utils.parser_media_handler import download_and_optimize_parsed_media

# Скачать и сохранить в R2 (или локальное хранилище)
r2_url = download_and_optimize_parsed_media(
    url=media_url,
    parser_name="instagram",   # имя парсера: instagram, ilacabak, zara, ...
    product_id=product_data.external_id,
    index=0,                   # 0 — главное, 1,2,... — галерея
    headers=optional_headers,
    timeout=15,
)
# r2_url — URL сохранённого файла в R2 (или пустая строка при ошибке)
```

Что делает функция:

- Скачивает файл по `url`.
- Определяет тип медиа (image / video / gif) по расширению (`storage_paths.detect_media_type`).
- Для **изображений** — оптимизирует (размер/качество) через `ImageOptimizer`.
- Сохраняет в R2 по пути из `get_parsed_media_upload_path(parser_name, media_type, filename)`.
- Возвращает публичный URL файла в R2 (или пустую строку при ошибке).

### 3.2. Структура путей в R2 для парсеров

Пути задаются в `apps.catalog.utils.storage_paths.get_parsed_media_upload_path`:

- Формат: `products/parsed/{parser_slug}/{media_type}s/{filename}`
- `parser_slug` — имя парсера в нижнем регистре, с дефисами (например, `instagram`, `ilacabak`).
- `media_type` — `image`, `video` или `gif`; в пути используется папка `images/`, `videos/` или `gifs/`.

Примеры:

- `products/parsed/instagram/images/instagram_abc123_0.jpg`
- `products/parsed/instagram/videos/instagram_abc123_0.mp4`
- `products/parsed/ilacabak/images/ilacabak_xyz_1.jpg`

Для каждого нового парсера отдельная подпапка создаётся автоматически по `parser_name`.

---

## 4. Сохранение спарсенных товаров в БД (команда/сервис)

Тот код, который получает список `ScrapedProduct` и пишет их в каталог (например, management-команда для Instagram или `ScraperIntegrationService`), должен:

1. Для каждого товара:
   - По `external_id` искать или создавать запись Product (или наследника).
   - Для главного изображения: вызвать `download_and_optimize_parsed_media(images[0], parser_name, product_id, 0)` и результат записать в поле **URL** товара (например, `main_image` у базового Product, если там хранится URL из R2).
   - Если есть видео — из `attributes['video_url']` при сохранении заполнять поле `video_url` у Product; при необходимости тот же URL можно передать в логику автоскачивания (см. ниже).
2. Для галереи (остальные элементы `images[1:]`):
   - Аналогично вызывать `download_and_optimize_parsed_media(url, parser_name, product_id, index)` и сохранять возвращённый URL в `ProductImage.image_url` (или аналог для типа товара).

Важно: в БД сохраняются именно **URL** медиа в R2, а не локальные пути и не сырые внешние URL (после того как медиа загружены в R2).

### 4.1. Автоскачивание из URL в R2 при сохранении (Product / ProductImage)

В проекте включены сигналы `pre_save` для Product и ProductImage:

- Если у экземпляра заполнены поля **URL** (`main_image`, `video_url` у Product; `image_url`, `video_url` у ProductImage), но не заполнены соответствующие **файловые** поля (`main_image_file`, `main_video_file`; `image_file`, `video_file`), то при сохранении медиа по этому URL автоматически скачивается и сохраняется в R2, а в файловое поле записывается уже путь в R2.

Поэтому парсер/команда могут при первом сохранении записать только URL (в т.ч. из R2 после `download_and_optimize_parsed_media`); при необходимости дублирование в файловые поля и повторное скачивание обрабатываются сигналами (обычно парсеры уже пишут в R2 через `download_and_optimize_parsed_media`, тогда в БД хранится R2 URL и файловые поля при желании можно заполнять отдельно или оставить логику сигналов для случаев прямого ввода URL в админке).

---

## 5. Чек-лист для нового парсера

1. **Класс парсера**
   - Создать в `backend/apps/scrapers/parsers/` класс, наследник `BaseScraper`.
   - Реализовать `get_name()`, `get_supported_domains()`, `parse_product_list`, `parse_product_detail`.
   - Возвращать `ScrapedProduct` с заполненными `name`, `url`, `external_id`, `images`, при необходимости `attributes['video_url']`, `attributes['is_video']`.

2. **Регистрация**
   - Зарегистрировать парсер в реестре: в `backend/apps/scrapers/parsers/registry.py` в функции `register_default_parsers()` добавить импорт и `_registry.register(YourParser)`.

3. **Загрузка медиа в R2**
   - В команде или сервисе, которые сохраняют результаты парсера в БД, для каждого URL медиа вызывать `download_and_optimize_parsed_media(url, parser_name=get_name(), product_id=..., index=...)`.
   - Использовать возвращённый URL для полей `main_image` / `image_url` / `video_url` в моделях каталога.

4. **Имя парсера**
   - Использовать одно и то же имя (например, `"my_site"`) в `get_name()` и в вызовах `download_and_optimize_parsed_media(..., parser_name="my_site", ...)`, чтобы все файлы попали в `products/parsed/my_site/`.

5. **Management-команда (по желанию)**
   - По аналогии с `run_instagram_scraper.py` можно добавить команду `run_<parser_name>_scraper.py`, которая вызывает парсер и сохраняет товары через общую логику загрузки медиа в R2.

6. **Конфигурация (по желанию)**
   - Если парсер запускается через `ScraperConfig` и `ScraperIntegrationService`, в конфиге должен быть указан `parser_class`, совпадающий с именем из `get_name()` (например, `instagram`).

---

## 6. Важные модули (ссылки в коде)

| Задача | Модуль / путь |
|--------|----------------|
| Базовый класс и структура товара | `backend/apps/scrapers/base/scraper.py` (`BaseScraper`, `ScrapedProduct`) |
| Загрузка медиа парсера в R2 | `backend/apps/catalog/utils/parser_media_handler.py` |
| Пути в R2, тип медиа | `backend/apps/catalog/utils/storage_paths.py` |
| Реестр парсеров | `backend/apps/scrapers/parsers/registry.py` |
| Пример парсера с R2 | `backend/apps/scrapers/management/commands/run_instagram_scraper.py` |
| Удаление файлов из R2 при удалении объекта | `backend/apps/catalog/signals.py` (post_delete) |
| Автоскачивание из URL в файловые поля | `backend/apps/catalog/signals.py` (pre_save для Product, ProductImage) |

---

## 7. Кратко: свойства парсера

- Возвращает данные в формате **ScrapedProduct** с URL медиа в `images` и при необходимости `attributes['video_url']`.
- **Не** пишет файлы в R2 сам; использует общую функцию **download_and_optimize_parsed_media** с единым именем парсера.
- Медиа в R2 раскладываются по путям **products/parsed/{parser_slug}/images|videos|gifs/**.
- В БД хранятся только ссылки на медиа в R2 (поля URL у Product/ProductImage); загрузку в R2 выполняет общий слой, так что каждый новый парсер автоматически получает свою папку в R2 и единообразное поведение.

Следуя этой инструкции, любой новый парсер для нового сайта будет корректно работать с R2 и каталогом без дублирования логики хранения медиа.
