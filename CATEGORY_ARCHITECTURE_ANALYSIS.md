# Анализ архитектуры категорий PharmaTurk

## Проблема после удаления БД

- **Много корневых категорий отсутствуют** — medicines, supplements, furniture, clothing, shoes, tableware, jewelry, accessories, perfumery и т.д.
- **Часть категорий остаётся** — antibiotics, painkillers, vitamins, minerals и т.п. (подкатегории из миграции 0024).
- **Причина**: корневые категории нигде не создаются миграциями, а только при первом использовании (скрапер, корзина).

---

## Текущая архитектура

### 1. Две сущности

| Сущность | Назначение | Где создаётся |
|----------|------------|---------------|
| **CategoryType** | Тип домена (Медицина, БАДы, Одежда...) | Миграция 0036 |
| **Category** | Конкретная категория товаров | Миграции, скрипты, get_or_create в коде |

### 2. Иерархия Category

- **Корневая категория**: `parent = null` — показывается на `/categories` и главной.
- **Подкатегория**: `parent` указывает на корневую Category.
- **category_type** (FK) — связь с CategoryType (medicines, supplements и т.д.).

### 3. Что ожидает фронтенд

- API `/catalog/categories?top_level=true` возвращает `Category.objects.filter(parent__isnull=True)`.
- На главной и `/categories` ожидаются корневые категории со slug: `medicines`, `supplements`, `clothing`, `shoes`, `electronics`, `furniture`, `tableware`, `accessories`, `jewelry`, `medical-equipment`, `underwear`, `headwear`, `perfumery`, `books`, `uslugi`.

---

## Где хардкод (разбросан по коду)

### 1. `backend/apps/orders/serializers.py` — CATEGORY_PRESETS

```python
CATEGORY_PRESETS = {
    'clothing': ('clothing', 'Одежда'),
    'shoes': ('shoes', 'Обувь'),
    'electronics': ('electronics', 'Электроника'),
    'medical_equipment': ('medical-equipment', 'Медицинская техника'),
}
```

Создаёт категории только при добавлении в корзину. Нет: medicines, supplements, furniture, tableware, jewelry, accessories, underwear, headwear, perfumery, books.

### 2. `backend/apps/scrapers/management/commands/run_instagram_scraper.py` — presets

```python
presets = {
    "clothing": ("clothing", "Одежда"),
    "shoes": ("shoes", "Обувь"),
    "electronics": ("electronics", "Электроника"),
    "furniture": ("furniture", "Мебель"),
    "tableware": ("tableware", "Посуда"),
    "accessories": ("accessories", "Аксессуары"),
    "jewelry": ("jewelry", "Украшения"),
    "underwear": ("underwear", "Нижнее бельё"),
    "headwear": ("headwear", "Головные уборы"),
    "books": ("books", "Книги"),
    "supplements": ("supplements", "БАДы"),
    "medical_equipment": ("medical-equipment", "Медтехника"),
    "medicines": ("medicines", "Медицина"),
}
```

Создаёт корневые категории только при запуске Instagram-скрапера.

### 3. `backend/apps/catalog/services.py` — CatalogNormalizer

```python
if cat_slug == "knigi" or normalized_name in {"книги", "книга", "books"}:
    books_category = Category.objects.filter(slug="books").first()
```

Хардкод slug `books` для категории книг.

### 4. `backend/apps/scrapers/services.py`

```python
books_category = Category.objects.filter(slug="books").first()
```

### 5. `backend/apps/catalog/migrations/0024_add_category_presets.py`

Создаёт **подкатегории** (antibiotics, painkillers, vitamins, living-room и т.д.) с `parent=null`:

- medicines → antibiotics, painkillers, cardio, dermatology...
- supplements → vitamins, minerals, omega-fish-oil...
- medical_equipment → measuring-devices, care-devices...
- tableware → kitchen-cookware, serving...
- furniture → living-room, bedroom...
- jewelry → rings, chains, bracelets...

Миграция **не создаёт** корневые Category с slug=medicines, supplements, furniture и т.д.

### 6. `frontend/src/pages/index.tsx` — categoryColorMap

```javascript
categoryColorMap = {
  medicines, supplements, clothing, underwear, headwear,
  shoes, electronics, furniture, tableware, accessories,
  jewelry, 'medical-equipment'
}
```

Ожидаемые slug категорий захардкожены на фронте.

---

## Почему после удаления БД всё ломается

1. **Миграция 0024** создаёт только подкатегории (antibiotics, vitamins, living-room и т.д.) с `parent=null`.
2. **Миграция 0036** создаёт только CategoryType, но не Category.
3. **Корневые Category** (medicines, supplements, furniture, clothing, shoes и т.д.) создаются только через:
   - `get_or_create` в `orders/serializers.py` (4 штуки: clothing, shoes, electronics, medical-equipment);
   - `get_or_create` в `run_instagram_scraper.py` (все остальные).

4. Если скрапер не запускали и в корзину не добавляли одежду/обувь/электронику — корневых категорий нет.
5. В итоге на `/categories` отображаются antibiotics, painkillers, vitamins и т.п. вместо medicines, supplements, furniture и т.д.

---

## Рекомендуемая архитектура

### Единый источник правды (Single Source of Truth)

Создать один модуль с полным списком корневых категорий и подкатегорий:

```
backend/apps/catalog/constants.py  (или category_presets.py)
```

### Структура данных

```python
ROOT_CATEGORIES = [
    ("medicines", "Медицина", "medicines"),
    ("supplements", "БАДы", "supplements"),
    ("medical-equipment", "Медтехника", "medical-equipment"),
    ("clothing", "Одежда", "clothing"),
    ("shoes", "Обувь", "shoes"),
    ("electronics", "Электроника", "electronics"),
    ("furniture", "Мебель", "furniture"),
    ("tableware", "Посуда", "tableware"),
    ("accessories", "Аксессуары", "accessories"),
    ("jewelry", "Украшения", "jewelry"),
    ("underwear", "Нижнее бельё", "underwear"),
    ("headwear", "Головные уборы", "headwear"),
    ("perfumery", "Парфюмерия", "perfumery"),
    ("books", "Книги", "books"),
    ("uslugi", "Услуги", "uslugi"),
]

SUBcategories = {
    "medicines": [
        ("Антибиотики", "antibiotics"),
        ("Обезболивающие", "painkillers"),
        # ...
    ],
    "supplements": [...],
    # ...
}
```

### Management command для seed

```bash
python manage.py seed_root_categories
```

Команда должна:

1. Создать/обновить CategoryType (если нужно).
2. Создать все корневые Category (slug, name, category_type, parent=null).
3. Создать подкатегории с `parent` = соответствующая корневая Category.
4. Обновить существующие подкатегории (antibiotics, vitamins и т.д.), установив им правильный `parent`.

### Рефакторинг кода

1. **orders/serializers.py** — импортировать `get_or_create_category(slug)` из общего модуля.
2. **run_instagram_scraper.py** — то же самое.
3. **catalog/services.py** — убрать хардкод `books`, использовать общую функцию.
4. **scrapers/services.py** — аналогично.

---

## План восстановления после удаления БД

1. Выполнить миграции: `python manage.py migrate`
2. Запустить seed: `python manage.py seed_catalog_data`

Команда `seed_catalog_data` создаёт:
- Типы категорий (CategoryType)
- Корневые категории с переводами ru/en
- Подкатегории с правильной иерархией (parent)
- Исправляет parent у подкатегорий из миграции 0024
- Бренды с переводами ru/en и primary_category_slug

Опции:
- `--categories-only` — только категории
- `--brands-only` — только бренды
- `--fix-hierarchy` — только исправить parent у подкатегорий

Скрипт идемпотентен: повторный запуск не создаёт дубликаты.

---

## Реализованное решение (2025)

- **Модуль констант**: `backend/apps/catalog/constants.py` — ROOT_CATEGORIES, SUB_CATEGORIES, BRANDS_DATA, `get_or_create_root_category()`
- **Management command**: `python manage.py seed_catalog_data`
- **Рефакторинг**: `orders/serializers.py` использует `get_or_create_root_category` из constants (парсеры не трогаем)
- **Админка**: единый раздел «Категории» для всех категорий, улучшен BrandAdmin с primary_category_slug в list_display/list_filter

### Обновления: «Украшения» и «Книги» доведены до эталона

- **Украшения**: отдельная модель `JewelryProduct` + эндпоинты `/api/catalog/jewelry/products`, включая фильтры по `gender`, `jewelry_type`, `material`; фронт использует отдельный API и карточки с вариантами.
- **Книги**: общий `Product` с book‑полями и отдельные фильтры (авторы, жанры, издательства, язык), фронт получает фильтры через `/api/catalog/products/book-filters` и грузит товары по `product_type=books`.

### Обновления: «Обувь»

- Фильтры по типу обуви и полу при множественном выборе работают как OR, а параметр `gender` в API передаётся только при одиночном выборе.
- Для обуви добавлена клиентская фильтрация по полу с детекцией токенов в `category`, `name`, `gender`, `variants.gender`, чтобы избежать ложных совпадений.

---

## Краткое резюме

| Проблема | Причина |
|----------|---------|
| Нет корневых категорий | Они не создавались миграциями, только при первом использовании |
| Остаются antibiotics, vitamins и т.д. | Их создаёт миграция 0024 с parent=null |
| Хардкод в разных местах | presets были разбросаны по orders, scrapers, catalog |

**Решение**: модуль `constants.py` + команда `seed_catalog_data` + рефакторинг `orders/serializers.py`.

---

## Категория «Украшения» — структура и поля для парсинга

### 1. Корневая категория и подкатегории

- **Тип категории**: `jewelry`
- **Корневая категория**: slug `jewelry`, URL `/categories/jewelry`
- **Подкатегории (slug)**:
  - `rings` (Кольца)
  - `chains` (Цепочки)
  - `bracelets` (Браслеты)
  - `earrings` (Серьги)
  - `pendants` (Подвески)
  - `wedding` (Обручальные)
  - `women` (Женские)
  - `men` (Мужские)

### 2. API эндпоинты

- **Список товаров**: `/api/catalog/jewelry/products`
- **Получение одного товара по slug**: `/api/catalog/jewelry/products/{slug}`
- **Бренды для фильтров**: `/api/catalog/brands?product_type=jewelry&primary_category_slug=jewelry`
- **Категории**: `/api/catalog/categories?slug=jewelry&include_children=true`

### 3. Модель данных (backend)

**JewelryProduct** — основной товар:
- `name` — название
- `slug` — уникальный slug
- `description` — описание
- `category` — ссылка на Category (подкатегория)
- `brand` — ссылка на Brand (может быть пустой)
- `gender` — `women | men | kids | unisex` (из `Category.GENDER_CHOICES`)
- `price`, `old_price`, `currency`
- `jewelry_type` — `ring | bracelet | necklace | earrings | pendant`
- `material` — материал изделия
- `metal_purity` — проба металла
- `stone_type` — тип камня
- `carat_weight` — вес камней
- `is_available`, `stock_quantity`
- `main_image`, `main_image_file`
- `video_url`, `main_video_file`
- `external_id`, `external_url`, `external_data`
- `is_active`, `is_featured`
- `created_at`, `updated_at`

**JewelryProductTranslation** — переводы товара:
- `locale` (`ru`, `en`)
- `name`
- `description`

**JewelryProductImage** — галерея товара:
- `image_url` или `image_file`
- `alt_text`
- `sort_order`
- `is_main`

**JewelryVariant** — варианты (цвет/материал/размеры):
- `name`, `name_en`
- `slug`
- `color`, `material`, `gender`
- `size` (устаревшее поле, лучше использовать `sizes`)
- `sku`, `barcode`, `gtin`, `mpn`
- `price`, `old_price`, `currency`
- `is_available`, `stock_quantity`
- `main_image`, `main_image_file`
- `external_id`, `external_url`, `external_data`
- `is_active`, `sort_order`

**JewelryVariantSize** — размеры внутри варианта:
- `size_value`
- `size_unit` (`mm`, `cm`, `standard`)
- `size_type` (`ring_size`, `bracelet_length`, `necklace_length`, `standard`)
- `size_display`
- `is_available`, `stock_quantity`, `sort_order`

**JewelryVariantImage** — галерея варианта:
- `image_url` или `image_file`
- `alt_text`
- `sort_order`
- `is_main`

### 4. Фильтры и параметры запроса

`/api/catalog/jewelry/products` поддерживает:
- `category_id` (массив ID)
- `category_slug` или `subcategory_slug` (slug или список через запятую)
- `brand_id` (поддержка массива, включая `other`)
- `gender` или `jewelry_gender` (например `women,men`)
- `jewelry_type` (например `ring,bracelet`)
- `material` (например `gold,silver`)
- `search` (по имени)
- `price_min`/`price_max` или `min_price`/`max_price`
- `ordering` (`name_asc`, `name_desc`, `price_asc`, `price_desc`, `newest`, `popular`)

### 5. Маппинг полей для парсинга

**Обязательный минимум:**
- Название → `JewelryProduct.name`
- Ссылка на товар → `JewelryProduct.external_url`
- Внешний ID → `JewelryProduct.external_id`
- Цена → `JewelryProduct.price` + `currency`
- Главное изображение → `JewelryProduct.main_image`

**Желательно парсить:**
- Описание → `JewelryProduct.description`
- Бренд → `Brand` (по имени/slug) или оставить пустым
- Подкатегория → `Category.slug` (rings, chains, bracelets, earrings, pendants, wedding)
- Тип украшения → `JewelryProduct.jewelry_type`
- Материал → `JewelryProduct.material`
- Проба металла → `JewelryProduct.metal_purity`
- Тип камня → `JewelryProduct.stone_type`
- Вес камней → `JewelryProduct.carat_weight`
- Пол → `JewelryProduct.gender`
- Наличие → `is_available`, `stock_quantity`
- Галерея → `JewelryProductImage[]`
- Видео → `video_url`

**Варианты (если есть опции/размеры/цвета):**
- Название варианта → `JewelryVariant.name` / `name_en`
- Цвет → `JewelryVariant.color`
- Материал → `JewelryVariant.material`
- Цена/старая цена → `JewelryVariant.price` / `old_price`
- Наличие → `JewelryVariant.is_available`, `stock_quantity`
- Размеры → `JewelryVariantSize[]`
- Изображения варианта → `JewelryVariantImage[]`

**Сырые данные парсинга:**
- Любые дополнительные поля сохранять в `external_data` (JSON) для повторной обработки.

### 6. Правила категорий и брендов

- Бренд **Other/Другое** трактуется как товары без бренда.
- Если бренд неизвестен — оставлять `brand = null`, а не создавать дубли.
- Для фильтров брендов использовать `product_type=jewelry`.

---

## Категория «Книги» — структура и поля для парсинга

### 1. Корневая категория и подкатегории

- **Тип категории**: `books`
- **Корневая категория**: slug `books`, URL `/categories/books`
- **Подкатегории**: жанры, `parent` = корневая `books`

### 2. API эндпоинты

- **Список товаров**: `/api/catalog/products?product_type=books`
- **Получение одного товара по slug**: `/api/catalog/products/{slug}`
- **Фильтры книг**: `/api/catalog/products/book-filters`
- **Категории**: `/api/catalog/categories?slug=books&include_children=true`

### 3. Модель данных (backend)

**Product** — базовая модель с полями книг:
- `isbn`, `publisher`, `publication_date`, `pages`, `language`
- `cover_type`, `rating`, `reviews_count`, `is_bestseller`, `is_new`
- `book_authors`, `book_genres`, `book_variants`

**BookVariant** — варианты (обложка/формат/цена):
- `cover_type`, `format_type`, `isbn`, `price`, `currency`, `main_image`, `is_active`

### 4. Фильтры и параметры запроса

`/api/catalog/products` для книг поддерживает:
- `author_id`, `genre_id`, `genre_slug`
- `publisher`, `language`
- `cover_type`, `format_type`, `isbn`
- `pages_min`, `pages_max`, `rating_min`, `rating_max`
- `is_available`, `availability_status`, `is_new`
- `min_price`, `max_price`, `ordering`

### 5. Маппинг полей для парсинга

**Обязательный минимум:**
- Название → `Product.name`
- Ссылка на товар → `Product.external_url`
- Внешний ID → `Product.external_id`
- Цена → `Product.price` + `currency`
- Главное изображение → `Product.main_image`

**Желательно парсить:**
- ISBN, издательство, страницы, язык
- Авторы → `ProductAuthor`
- Жанры → `ProductGenre`
- Обложка/формат → `BookVariant.cover_type`, `BookVariant.format_type`

---

## Сравнение корневых категорий с логикой «Украшения»

### 1. Карта корневых категорий и текущая модель/эндпоинты

**Есть отдельные модели и отдельные эндпоинты (приближены к «Украшениям»):**
- **Одежда** — `ClothingProduct`, `/api/catalog/clothing/products`
- **Обувь** — `ShoeProduct`, `/api/catalog/shoes/products`
- **Электроника** — `ElectronicsProduct`, `/api/catalog/electronics/products`
- **Украшения** — `JewelryProduct`, `/api/catalog/jewelry/products`
- **Мебель** — `FurnitureProduct`, `/api/catalog/furniture/products` (в бекенде есть, фронт не использует)

**Используют общую модель Product и общий эндпоинт:**
- Медицина, БАДы, Медтехника
- Посуда, Аксессуары
- Нижнее бельё, Головные уборы
- Книги, Парфюмерия
- Услуги, Спорттовары, Автозапчасти, Исламская одежда, Благовония

### 2. Сопоставление «работоспособности» с «Украшения»

**Полная или близкая совместимость:**
- **Одежда/Обувь**: есть варианты, размеры, изображения, перевод, фильтры в API и фронте
- **Электроника**: отдельная модель и API, но нет вариантов и размеров

**Частичная совместимость:**
- **Мебель**: отдельная модель и API на бекенде, но фронт по умолчанию ходит в общий `/api/catalog/products`, из‑за чего товары мебели могут не отображаться (если они хранятся в `FurnitureProduct`)

**Низкая совместимость (как у «Украшения»):**
- **Underwear/Headwear/Accessories/Tableware/Perfumery/Books/…** — нет отдельной модели, нет вариантов и размеров, фильтрация в основном общая

### 3. Ключевые несовпадения логики

- **Front‑end routing API**: `getApiForCategory()` не включает `furniture`, поэтому мебель не использует свой API.  
  [api.ts](file:///Users/user/PharmaTurk/frontend/src/lib/api.ts#L176-L221), [categories/[slug].tsx](file:///Users/user/PharmaTurk/frontend/src/pages/categories/[slug].tsx#L214-L229)
- **Подкатегории в сайдбаре**: отдельные секции есть только для `medicines`, `clothing`, `books`, `perfumery`.  
  [categories/[slug].tsx](file:///Users/user/PharmaTurk/frontend/src/pages/categories/[slug].tsx#L638-L759)
- **Счётчики брендов**: `BrandSerializer` считает `products_count` только по `Product`, а для отдельных моделей (clothing/shoes/jewelry/…) счётчик не отражает реальное количество.  
  [serializers.py](file:///Users/user/PharmaTurk/backend/apps/catalog/serializers.py#L225-L247)

---

## План рекомендаций по выравниванию категорий до уровня «Украшения»

### Шаг 1. Выравнять фронт‑энд маршрутизацию по API

- Добавить `furnitureApi` и включить `furniture` в `getApiForCategory()`.
- Уточнить `resolveProductsEndpoint()` для мебели, чтобы SSR ходил в `/api/catalog/furniture/products`.
- При необходимости — добавить API для `perfumery`, `books`, `underwear`, `headwear`, если решим выводить их из общей модели в отдельные.

### Шаг 2. Выравнять работу брендов и их счётчиков

- Сделать `BrandSerializer.products_count` агрегированным по тем же моделям, что и `CategorySerializer`.

---

## План приведения категории «Обувь» к эталону

### 1. Данные и иерархия
- Убедиться, что корневая категория `shoes` создана и связана с `CategoryType`.
- Проверить подкатегории и их `parent`, корректные `shoe_type` и `gender`.

### 2. Бэкенд API
- Подтвердить покрытие фильтров `size`, `color`, `material`, `heel_height`, `gender` и `is_new` в `ShoeProductViewSet`.
- Синхронизировать описания параметров в `extend_schema` с фактическими фильтрами.

### 3. Фронтенд: маршрутизация и фильтры
- Проверить `getApiForCategory()` и `resolveProductsEndpoint()` для `shoes` (должен быть отдельный API).
- Сопоставить фильтры сайдбара с параметрами API: пол, размеры, цвет, материал, «Новинки».

### 4. Карточка и товарная страница
- Убедиться, что `ShoeProduct` и варианты корректно отрисованы (варианты, размеры, изображения).
- Проверить `resolveDetailEndpoint()` для `shoes` и редиректы по типу товара.

### 5. Импорт и парсинг
- В маппинге парсеров использовать `product_type=shoes`, `category` по `shoe_type`/slug.
- Заполнять `ShoeVariant` и размеры в `ShoeVariantSize`, если доступны.

### 6. Проверки
- SSR список и фильтры на `/categories/shoes`.
- Корректность пагинации и счётчиков.
- Сравнение выдачи с эталоном (Украшения/Книги).
- Либо вернуть в API `product_count` (aliased), чтобы фронт не зависел от конкретного поля.
- Проверить фильтрацию брендов по `product_type` для всех корневых категорий.

### Шаг 3. Определить категории, которым нужны варианты/размеры/цвета

**Рекомендации для выноса в отдельные модели (как у одежды/обуви/украшений):**
- **Underwear** — размеры и варианты цветов практически обязательны
- **Headwear** — размеры/обхват, варианты материалов и цветов
- **Accessories** — часто требует вариантов (цвет/материал/размер), особенно ремни/сумки
- **Tableware** — варианты по материалу/цвету/объёму, наборы
- **Perfumery** — варианты по объёму, концентрации (EDT/EDP/Parfum)
- **Books** — варианты по формату (hardcover/paperback/ebook), языку

### Шаг 4. Нормализовать фильтры и подкатегории

- Ввести единый формат: `material`, `size`, `color`, `gender`, `type` для категорий с вариантами.
- Для категорий с кастомными фильтрами (headwear/clothing/shoes) перенести часть логики из фронта в API.
- Обновить структуру подкатегорий в сайдбаре для новых корневых категорий.

### Шаг 5. Проработка миграций данных

- Если категория переводится в отдельную модель — добавить миграцию переносов (`Product → NewModel`).
- Для парсинга добавить сохранение «сырого» JSON в `external_data`.

---

## Детализация по корневым категориям (готовность и разрывы)

### 1. Категории с отдельными моделями и вариативностью

**Одежда**  
Готовность: высокая.  
Есть модели вариантов/размеров/изображений и фильтры.  
См. [models.py](file:///Users/user/PharmaTurk/backend/apps/catalog/models.py#L1661-L1535), [views.py](file:///Users/user/PharmaTurk/backend/apps/catalog/views.py#L923-L1065)

**Обувь**  
Готовность: высокая.  
Есть варианты/размеры/изображения, фильтры по размеру/цвету/материалу.  
См. [models.py](file:///Users/user/PharmaTurk/backend/apps/catalog/models.py#L1898-L2260), [views.py](file:///Users/user/PharmaTurk/backend/apps/catalog/views.py#L1076-L1260)

**Украшения**  
Готовность: высокая.  
Есть варианты/размеры/изображения, расширенные поля.  
См. [models.py](file:///Users/user/PharmaTurk/backend/apps/catalog/models.py#L2296-L2736), [views.py](file:///Users/user/PharmaTurk/backend/apps/catalog/views.py#L1401-L1488)

### 2. Категории с отдельными моделями, но без вариативности

**Электроника**  
Готовность: средняя.  
Отдельная модель и API, но нет вариантов/цветов/размеров.  
См. [models.py](file:///Users/user/PharmaTurk/backend/apps/catalog/models.py#L2741-L3061), [views.py](file:///Users/user/PharmaTurk/backend/apps/catalog/views.py#L1260-L1388)

**Мебель**  
Готовность: средняя.  
Есть отдельная модель и API, но фронт запрашивает общий `/api/catalog/products`, из‑за чего товары мебели могут не появляться.  
См. [api.ts](file:///Users/user/PharmaTurk/frontend/src/lib/api.ts#L176-L221), [categories/[slug].tsx](file:///Users/user/PharmaTurk/frontend/src/pages/categories/[slug].tsx#L214-L229)

### 3. Категории на общей модели Product

**Медицина/БАДы/Медтехника**  
Готовность: средняя.  
Общий продукт, есть фильтры по цене/наличию/атрибутам, но нет вариантов и размеров.  
См. [views.py](file:///Users/user/PharmaTurk/backend/apps/catalog/views.py#L551-L641)

**Books/Perfumery/Underwear/Headwear/Accessories/Tableware/Services/Sports/Auto‑parts/Islamic‑clothing/Incense**  
Готовность: низкая.  
Общий продукт без вариантов, логика фильтров в основном фронтовая/ограниченная.

---

## Риски и несоответствия, влияющие на работоспособность

- **Мебель**: нет использования отдельного API на фронте (список/деталь).  
  [api.ts](file:///Users/user/PharmaTurk/frontend/src/lib/api.ts#L176-L221), [product/[[...slug]].tsx](file:///Users/user/PharmaTurk/frontend/src/pages/product/[[...slug]].tsx#L35-L57)
- **Бренды для “нестандартных” типов**: `brandProductTypeMap` не содержит `sports`, `auto-parts`, `islamic-clothing`, `incense`, поэтому запросы брендов идут как `product_type=medicines`.  
  [categories/[slug].tsx](file:///Users/user/PharmaTurk/frontend/src/pages/categories/[slug].tsx#L107-L123)
- **Несовпадение slug ↔ product_type**: в бекенде `auto_parts`, `islamic_clothing`, в URL используются `auto-parts`, `islamic-clothing`. Нужна нормализация на API либо mapping на фронте.
- **Счётчики брендов**: `BrandSerializer.products_count` учитывает только `Product`, не считает отдельные модели (clothing/shoes/jewelry/etc).

---

## Категории, которым нужны отдельные модели с вариантами

### 1. Underwear (нижнее бельё)

**Причина**: размеры, чашки, цвета, тип ткани.  
**Рекомендуемые поля варианта**:
- `size`, `cup`, `band_size`, `color`, `material`, `price`, `stock_quantity`

### 2. Headwear (головные уборы)

**Причина**: размеры, обхват головы, сезонность, материалы.  
**Рекомендуемые поля варианта**:
- `size`, `head_circumference`, `season`, `material`, `color`

### 3. Accessories (аксессуары)

**Причина**: часто разные материалы/цвета/размеры (ремни, сумки).  
**Рекомендуемые поля варианта**:
- `size`, `material`, `color`, `hardware_color`, `strap_length`

### 4. Tableware (посуда)

**Причина**: объём, материал, наборы, количество предметов.  
**Рекомендуемые поля варианта**:
- `volume_ml`, `material`, `color`, `set_size`, `diameter`, `height`

### 5. Perfumery (парфюмерия)

**Причина**: объём, концентрация, пол/тип аромата.  
**Рекомендуемые поля варианта**:
- `volume_ml`, `concentration` (EDT/EDP/Parfum), `gender`, `note_profile`

### 6. Books (книги)

**Причина**: формат, язык, переплёт, ISBN.  
**Рекомендуемые поля варианта**:
- `format`, `language`, `binding`, `pages`, `isbn`

### 7. Sports / Auto‑parts / Islamic‑clothing / Incense

**Sports**: размеры/уровни/наборы.  
**Auto‑parts**: совместимость (марка/модель/год/двигатель).  
**Islamic‑clothing**: как clothing (размер/цвет/материал).  
**Incense**: форма (палочки/конусы/саше), объём/вес, аромат.

---

## Рекомендуемые следующие изменения (кратко)

1. Добавить `furniture` в фронтовые API роутеры и детали товаров.
2. Нормализовать `product_type` slug↔underscore для auto‑parts/islamic‑clothing.
3. Расширить `brandProductTypeMap` и `BrandViewSet` для всех корневых категорий.
4. Определить список категорий, которые переводятся на отдельные модели, и подготовить миграции.
