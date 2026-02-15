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

---

## Краткое резюме

| Проблема | Причина |
|----------|---------|
| Нет корневых категорий | Они не создавались миграциями, только при первом использовании |
| Остаются antibiotics, vitamins и т.д. | Их создаёт миграция 0024 с parent=null |
| Хардкод в разных местах | presets были разбросаны по orders, scrapers, catalog |

**Решение**: модуль `constants.py` + команда `seed_catalog_data` + рефакторинг `orders/serializers.py`.
