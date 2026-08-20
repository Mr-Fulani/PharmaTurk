# Локализация категорий

## Текущая архитектура

Основной источник переводов категорий — модель backend
`CategoryTranslation`. API отдаёт её записи в поле `translations` каждой
категории:

```json
{
  "id": 42,
  "slug": "medical-equipment",
  "name": "Медицинский инвентарь",
  "description": "...",
  "translations": [
    { "locale": "ru", "name": "Медицинский инвентарь", "description": "..." },
    { "locale": "en", "name": "Medical Equipment", "description": "..." }
  ]
}
```

`frontend/src/lib/i18n.ts` выбирает название в таком порядке:

1. `translations[]` из API для текущей locale;
2. JSON-ключ `category_{normalized-slug}_name`;
3. совместимые JSON fallback-ключи `filter_*` и `attr_val_*`;
4. поле `name` из API.

При непустом базовом description порядок для описания такой: API translation →
JSON-ключ `category_{normalized-slug}_description` → поле `description` из API.
Статические JSON-ключи — страховочный fallback для legacy-контента, а не
основная база переводов.

Backend-модель сейчас поддерживает locale `ru` и `en`. Slug для JSON-ключей
нормализуется: приводится к нижнему регистру, `_` заменяется на `-`.

## Как добавить или изменить категорию

### 1. Добавьте переводы в backend

Создайте/измените категорию в Django admin и заполните связанные записи
`CategoryTranslation` минимум для `ru` и `en`. Для каждой пары
`category + locale` разрешена одна запись.

Заполняйте обе локали даже при наличии базового `Category.name`: это делает API
самодостаточным для frontend, SSR и других клиентов.

### 2. Проверьте API

Ответ списка или detail категории должен содержать обе записи:

```text
GET /api/catalog/categories/?slug=new-category
```

Проверьте `translations[].locale`, `name` и при необходимости `description`.
Frontend не должен угадывать перевод из slug, если он уже есть в API.

### 3. Добавьте JSON fallback только при необходимости

Если категория должна корректно отображаться при временно неполном API-ответе,
добавьте ключи в:

- `frontend/public/locales/ru/common.json`;
- `frontend/public/locales/en/common.json`.

```json
{
  "category_new-category_name": "Новая категория",
  "category_new-category_description": "Описание новой категории"
}
```

```json
{
  "category_new-category_name": "New Category",
  "category_new-category_description": "New category description"
}
```

Не добавляйте новую категорию в несколько статических TypeScript maps: это
создаёт расходящиеся источники правды.

## Где используется

- главная страница и `/categories` вызывают
  `getLocalizedCategoryName` / `getLocalizedCategoryDescription`;
- `/categories/[slug]` использует те же helpers после гидрации;
- `CategorySidebar` локализует дерево и жанры через `translations` из API;
- backend `CategorySerializer.name` также учитывает язык запроса, но frontend
  всё равно предпочитает явный массив `translations`.

При серверных запросах передавайте корректный `Accept-Language`, а locale в
frontend helpers берите из `router.locale`. Не определяйте язык по браузеру
вручную в компонентах.

## Известные несоответствия SSR

На странице `frontend/src/pages/categories/[slug].tsx` сохранилась legacy-функция
`getCategoryNames`. Для известных корневых типов она выбирается раньше данных
`CategoryTranslation`, поэтому первый SSR HTML может использовать статическое
название, а после гидрации — перевод API. Кроме того, не все запросы категорий в
`getServerSideProps` передают `Accept-Language`.

Целевое улучшение: вычислять `categoryName` и `categoryDescription` на SSR из
`mainCat.translations` для текущей locale, затем использовать JSON/static
fallback. После этого `getCategoryNames` можно удалить. До такого рефакторинга
изменения переводов корневых категорий нужно проверять и в SSR HTML, и после
гидрации.

Есть ещё одна текущая особенность helper: `getLocalizedCategoryDescription`
возвращает `null`, если базовое `fallbackDescription` пустое, ещё до проверки
`translations`. Пока это не исправлено, заполняйте базовое описание категории,
если локализованное описание должно отображаться.

## Проверка

1. Откройте главную, `/categories` и `/categories/{slug}` на `ru` и `en`.
2. Проверьте карточку, заголовок, описание, breadcrumbs и sidebar.
3. Отключите JavaScript или посмотрите HTML ответа, чтобы проверить SSR отдельно
   от гидрации.
4. Убедитесь, что неизвестный перевод корректно падает обратно к JSON, а затем
   к backend name, без отображения сырого i18n key.
5. Выполните frontend typecheck и тесты, затрагивающие локализацию.

## Историческая справка: инцидент `uslugi`

Ранее категория `uslugi` отсутствовала одновременно в клиентском mapping,
серверном mapping и JSON-файлах, поэтому её название не переводилось. Добавление
`category_uslugi_*` устранило симптом, но современное решение — хранить перевод
в `CategoryTranslation` и оставлять JSON лишь fallback. Этот раздел описывает
причину старого инцидента, а не рекомендуемую архитектуру.
