# Избранное, идентификаторы доменных товаров, proxy-медиа и R2

Документ для разработчиков и ассистентов: контекст правок (апрель 2026), связанных с избранным, headwear/underwear/islamic-clothing, нагрузкой на R2 и Next.js proxy.

---

## 1. Модель и API избранного

- **Модель** `Favorite` (`backend/apps/catalog/models.py`): generic FK — пары `(content_type_id, object_id)` плюс `user` или `session_key`. Уникальность: одна запись на пару `(user|session, content_type, object_id)`.
- **ViewSet** `FavoriteViewSet` (`backend/apps/catalog/views.py`): `list`, `add`, `remove`, `check`, `count`.
- **Сериализация товара в списке** — `FavoriteSerializer.get_product`: в зависимости от класса инстанса выбирается нужный сериализатор (обувь, headwear и т.д.). Для **headwear / underwear / islamic_clothing** в ответе поле `product.id` **приводится к id shadow `Product`** (`base_product_id`), чтобы совпадать с корзиной и единым контрактом фронта (`_pin_base_product_fields`).

---

## 2. Проблема «разные товары конфликтуют» и неверное добавление

**Симптомы:** на проде казалось, что обувь и головной убор «перепутаны»; в избранном дублировались карточки с одним названием; с карточки категории headwear звезда не загоралась после добавления, повторный клик давал **400 «Товар уже в избранном»**.

**Причины:**

1. **Старый маппинг в `AddToFavoriteSerializer`:** для `headwear` / `underwear` / `islamic_clothing` брался `Product.objects.get(id=product_id)`, тогда как в листингах на фронт уходит **id доменной строки** (`HeadwearProduct.id` и т.п.), как для обуви (`ShoeProduct`). Числовой `id` совпадал с другой таблицей → в избранное попадал **чужой** `Product`.

2. **Расхождение id после добавления:** в `/favorites` для headwear trio в `product.id` отдаётся **base (shadow) id**, а карточка категории передавала в API избранного **доменный id** без `base_product_id` в JSON листинга → `isFavorite` на клиенте не находил запись.

3. **Дубликаты в списке:** в БД могли сосуществовать две записи на одну витринную позицию (например, старый `Favorite` на `Product` и новый на `ShoeProduct` / доменную модель с тем же slug).

---

## 3. Бэкенд: единая резолвация и legacy

**Функция** `resolve_product_for_favorites_api` в `backend/apps/catalog/serializers.py` (используется в `AddToFavoriteSerializer` и в `FavoriteViewSet.check`):

- Нормализует `product_type` (в т.ч. алиасы вроде `medical_accessories` → `accessories`).
- Для **headwear / underwear / islamic_clothing** по порядку:
  - `DomainModel.objects.get(id=product_id)`;
  - иначе `DomainModel.objects.filter(base_product_id=product_id).first()`;
  - иначе `Product.objects.get(id=product_id)` и обратная связь `headwear_item` / `underwear_item` / `islamic_clothing_item`.
- Остальные типы — прежний `PRODUCT_MODEL_MAP` (обувь, одежда, `Product` для generic и т.д.).

**`FavoriteViewSet.add`:** перед `get_or_create` для `HeadwearProduct` / `UnderwearProduct` / `IslamicClothingProduct` удаляются устаревшие записи с **тем же** `base_product_id`, но с `content_type = Product` (миграция поведения без отдельной data-migration).

**`FavoriteViewSet.remove`:** удаляет и доменную запись, и legacy `Product` с тем же `base_product_id` для этих трёх типов.

**`FavoriteViewSet.check`:** учитывает и доменную запись, и legacy `Product` по `base_product_id`.

**Дедупликация ответа `list` и `count`:** функция `_dedupe_favorites_serialized_rows` в `views.py` после сериализации оставляет одну запись на ключ `(slug, нормализованный _product_type)`, предпочитая более новую по `created_at`. Так счётчик `count` совпадает с длиной видимого списка.

---

## 4. Бэкенд: листинг headwear / underwear / islamic

В **`HeadwearProductSerializer`**, **`UnderwearProductSerializer`**, **`IslamicClothingProductSerializer`** в `Meta.fields` добавлено поле **`base_product_id`** (read-only с модели). Без него фронт не мог вычислить тот же id, что в ответе `/favorites`, для `favoriteApiProductId`.

---

## 5. Фронтенд

**`frontend/src/lib/product.ts`:**

- `favoriteApiProductId({ id, base_product_id }, productType)` — для типов `headwear`, `underwear`, `islamic-clothing` в запросы add/remove/check подставляется **`base_product_id`**, если он есть; иначе `id`.

**`ProductCard`**, страница товара **`[[...slug]].tsx`**, **`PopularProductsCarousel`:** передают в `FavoriteButton` `productId={favoriteApiProductId(...)}` где нужно.

**`frontend/src/store/favorites.ts`:** в `isFavorite` типы сравниваются в нормализованном виде (`_` → `-`, lower), чтобы совпадать с `_product_type` из API.

**`FavoriteButton`:**

- Подписка на стор через **`zustand/shallow`** с включением **`favorites`**, чтобы после `refresh()` кнопка перерисовывалась (стабильные ссылки на `add`/`remove`/`isFavorite` сами по себе не гарантировали подписку на массив).
- При ответе «уже в избранном» на add — вызывается **`refresh()`** без алерта (синхронизация UI после рассинхрона).

---

## 6. Proxy-медиа, R2 и Next.js (устойчивость под нагрузкой)

**Симптомы:** при лавине запросов к `/api/catalog/proxy-media/` — `urllib3` «pool is full» к R2, обрывы у Next proxy к бэкенду.

**Бэкенд** (`backend/config/settings.py`, при `USE_R2`):

- Для `S3Boto3Storage` в `OPTIONS` передаётся `client_config` из `botocore.config.Config`:
  - **`R2_BOTO_MAX_POOL_CONNECTIONS`** (env, по умолчанию `64`) — `max_pool_connections`;
  - `connect_timeout=10`, `read_timeout=300`.

**Фронт** (`frontend/next.config.js`):

- `experimental.proxyTimeout` из **`NEXT_PROXY_TIMEOUT_MS`** (по умолчанию `180000` мс) для rewrites `/api/*` → backend (длинные ответы прокси).

**Страница списка категорий** (`frontend/src/pages/categories/index.tsx`): у изображений категорий — `loading="lazy"`, `decoding="async"` (меньше одновременной нагрузки).

---

## 7. `GET /api/catalog/products/resolve/{slug}` и варианты обуви

Страница товара (`frontend/src/pages/product/[[...slug]].tsx`) берёт данные через **resolve**, а не напрямую из `shoes/products/...`.

**Порядок в `resolve_product_payload`** (`backend/apps/catalog/services/product_resolve.py`): сначала перебираются **доменные** ViewSet (в т.ч. `ShoeProductViewSet`), затем generic **`ProductViewSet`**. Если делать наоборот, shadow `Product` с тем же `slug`, что и родительская пара обуви, отдавался бы **`ProductSerializer`** без поля **`variants`** — на фронте пропадали цвета, размерные ряды и часть медиа. Доменная строка `ShoeProduct` должна выигрывать при совпадении slug.

---

## 8. Файлы кода (ориентир)

| Область | Файлы |
|--------|--------|
| Резолвация избранного | `backend/apps/catalog/serializers.py` — `resolve_product_for_favorites_api`, `AddToFavoriteSerializer`, `FavoriteSerializer` |
| API избранного | `backend/apps/catalog/views.py` — `FavoriteViewSet`, `_dedupe_favorites_serialized_rows` |
| ID для API на фронте | `frontend/src/lib/product.ts` — `favoriteApiProductId` |
| Стор и кнопка | `frontend/src/store/favorites.ts`, `frontend/src/components/FavoriteButton.tsx` |
| Карточки | `frontend/src/components/ProductCard.tsx`, `frontend/src/pages/categories/[slug].tsx` |
| R2 / proxy | `backend/config/settings.py`, `frontend/next.config.js` |
| Resolve карточки (SSR/клиент) | `backend/apps/catalog/services/product_resolve.py` |

---

## 9. Что проверять после изменений в каталоге

- Новый доменный тип с shadow `Product`: нужны ли он в `resolve_product_for_favorites_api`, в `FavoriteSerializer.get_product`, и отдаётся ли в листинге **`base_product_id`**, если в избранном пинится base id.
- Любое изменение `_product_type` в API — синхронизировать нормализацию на фронте (`favoriteApiProductId`, `isFavorite`).
- При добавлении путей прокси медиа — следить за пулом соединений к R2 и таймаутом Next.
- Не возвращать **generic Product** раньше домена для slug, по которому существует `ShoeProduct` / `ClothingProduct` с вариантами — иначе сломается страница товара.
