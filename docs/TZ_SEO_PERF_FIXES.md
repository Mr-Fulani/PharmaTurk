# ТЗ для агента: исправление SEO-индексации и производительности Mudaroba

Контекст: Next.js 14 pages router, i18n `{ defaultLocale: 'ru', locales: ['en','ru'] }` → ru-страницы живут **без префикса**, en — под `/en`. Путь `/ru/...` в pages router **отдаёт 404** (префикс дефолтной локали не обслуживается). Бэкенд — Django/DRF за nginx и Cloudflare. Прод-домен `https://mudaroba.com`.

Выполнять этапы строго по порядку, каждый этап — отдельная ветка и отдельный коммит(ы). После каждого этапа — раздел «Проверка» обязателен. Ничего за пределами ТЗ не менять.

> **Статус:** этапы 1–3 выполнены 2026-06-12 в ветке `seo/p0-locale-redirects`.
> Важная поправка по фактам: `/ru/*` в Next 14 — это 200-дубликат, а не 404
> (проверено на прод-сборке). Поэтому к этапу 1 добавлен 301 `/ru/* → /*` на
> nginx (в Next не решается: i18n-нормализация срезает префикс до
> middleware/redirects). Этапы 4–10 — не начаты.

---

## Этап 1 (P0): локальный префикс в редиректах карточки товара

**Файл:** `frontend/src/pages/product/[[...slug]].tsx`, getServerSideProps (~строка 2647).

**Проблема:** `const localePrefix = ctx.locale ? `/${ctx.locale}` : ''` — для `ru` даёт редиректы на `/ru/product/...` → 404. Затронуты все три redirect-ветки gSSP (canonical_path, несовпадение типа, вариант→база).

**Сделать:**
1. Заменить на:
   ```ts
   const localePrefix = ctx.locale && ctx.locale !== ctx.defaultLocale ? `/${ctx.locale}` : ''
   ```
2. Прогрепать весь `frontend/src` на `ctx.locale ?` и `'/' + ctx.locale` / шаблоны `` `/${ctx.locale}` `` в gSSP — починить все места с тем же багом.

**Проверка:**
- `npm run build` зелёный.
- Локально (`npm run dev` или прод-сборка): `curl -sI "http://localhost:3000/product/<тип>/<slug-с-несовпадающим-типом>"` → `Location` НЕ начинается с `/ru`.
- `curl -sI http://localhost:3000/ru/` → 404 (подтверждение поведения роутера, зафиксировать в отчёте).

## Этап 2 (P0): 5xx бэкенда не должны превращаться в 404

**Файлы:** `product/[[...slug]].tsx` (~2728), а также gSSP в `categories/[slug].tsx`, `brand/[slug].tsx`, `[slug].tsx`, `testimonials/[id].tsx`.

**Сделать:** в каждом catch различать:
```ts
} catch (err) {
  if (axios.isAxiosError(err) && err.response?.status === 404) {
    return { notFound: true }
  }
  throw err // Next отдаст 500 — бот сохранит страницу в индексе
}
```
Аналогично: `notFound` только при явном 404 API.

**Проверка:** остановить бэкенд, запросить карточку — ответ 500 (не 404). Юнит не требуется, ручной проверки достаточно; результат — в отчёт.

## Этап 3 (P0): единый SEO-компонент и починка canonical на сломанных страницах

**Шаг 3.1.** Починить `frontend/src/components/SEO.tsx`:
- canonical: `localePrefix = locale === router.defaultLocale ? '' : '/'+locale`; ru → без префикса, en → `/en`.
- Добавить в компонент hreflang-тройку: `ru` (без префикса), `en` (`/en`), `x-default` (= ru).
- При `noindex` — не выводить canonical и hreflang.

**Шаг 3.2.** Перевести на компонент страницы со сломанной/отсутствующей метой (минимально-инвазивно, контент меты сохранить):
- `testimonials/index.tsx` (canonical захардкожен на ru)
- `testimonials/[id].tsx` (canonical без префикса локали)
- `how-to-order-medicines.tsx` (захардкожен)
- `categories/[slug]/works.tsx` (без префикса, без hreflang)
- `categories/index.tsx` (canonical отсутствует)

Остальные страницы (index, product, categories/[slug], brand/*, brands, privacy, delivery, returns, [slug]) — НЕ трогать в этом этапе: их canonical корректен.

**Шаг 3.3.** `_document.tsx`: удалить глобальные `og:url`, `og:type`, hreflang-теги (строки ~58-59, 67-71) — они дублируют постраничные и вешаются на noindex-страницы. `og:site_name`, theme-color, верификации, GTM — оставить.

**Проверка:** для каждой изменённой страницы, обе локали:
```bash
curl -s http://localhost:3000/testimonials | grep -E 'canonical|hreflang'
curl -s http://localhost:3000/en/testimonials | grep -E 'canonical|hreflang'
```
Ожидание: canonical самоссылающийся (en-страница → `/en/...`), hreflang-тройка одинакова на обеих локалях, дублей нет (по одному тегу каждого вида на страницу).

## Этап 4 (P1): убрать расхождение двух sitemap

**Файлы:** `backend/api/seo.py`, `backend/api/urls.py` (или где он подключён).

**Сделать:** найти, по какому URL отдаётся бэкендовый sitemap/robots (`grep -rn "sitemap" backend/api/urls.py backend/config/urls.py`). Если он доступен снаружи — удалить эндпоинты (источник правды — фронтовый `/sitemap.xml`). Если используется только как fallback — удалить всё равно, fallback с расходящимися URL вреднее отсутствия.

**Проверка:** `curl -sI https://<backend-host>/sitemap.xml` → 404 после деплоя; фронтовый `/sitemap.xml` работает.

## Этап 5 (P1): кэширование SSR-HTML

**Файлы:** gSSP в `product/[[...slug]].tsx`, `categories/[slug].tsx`, `categories/index.tsx`, `brand/[slug].tsx`, `brands/index.tsx`, `testimonials/*`.

**Сделать:** в начале gSSP (как уже сделано в `index.tsx:548`):
```ts
ctx.res.setHeader('Cache-Control', 'public, s-maxage=300, stale-while-revalidate=86400')
```
Важно: HTML карточки зависит от cookie `currency` (SSR читает её). Чтобы кэш не отдавал чужую валюту: на карточке товара ставить `private, no-store`, ЕСЛИ в запросе есть cookie `currency`, иначе публичный кэш. (Категории не читают currency в SSR — проверить grep-ом и кэшировать безусловно.)

**Проверка:** `curl -sI` каждой страницы → заголовок присутствует; с cookie `currency=USD` карточка отдаёт `private`.

**Отметить в отчёте:** для реального эффекта нужна Cloudflare Cache Rule «Cache eligible: HTML, respect origin headers» — настраивается в панели CF вручную (агенту недоступно).

## Этап 6 (P1): ускорить resolve товара (до 20 последовательных dispatch)

**Файл:** `backend/apps/catalog/services/product_resolve.py`.

**Сделать:**
1. Перед перебором ViewSet-ов определить тип одним-двумя запросами:
   - `Product.objects.filter(slug=slug, is_active=True).values_list('product_type', flat=True).first()`
   - если нашёлся — диспатчить только в соответствующий доменный ViewSet (маппинг `product_type → ViewSet` из `_domain_viewsets_order`), при его 404 — fallback в generic `ProductViewSet`;
   - если не нашёлся — проверить `Service` (uslugi), затем текущий полный перебор как последний fallback (доменные модели с отдельными слагами вариантов).
2. Кэшировать положительный результат `slug → (source_key, product_type)` в Redis на 1 час (`cache.set(f"resolve_pt:v1:{slug}", ...)`); инвалидация не требуется — TTL достаточно, при смене типа отработает canonical-redirect.
3. Существующие тесты resolve не ломать (`backend/apps/catalog/tests/` — найти и прогнать).

**Проверка:** `pytest backend/apps/catalog -k resolve` зелёный; вручную: `curl "http://localhost:8000/api/catalog/products/resolve/<slug>"` для slug каждого из трёх путей (доменный, generic, услуга) — ответы идентичны прежним (сравнить JSON до/после).

## Этап 7 (P1): proxy-media — кэш до R2, threads для gunicorn

**Файлы:** `backend/apps/catalog/views.py` (proxy_media, ~3125), `backend/docker-entrypoint.sh`.

**Сделать:**
1. В `proxy_media` при наличии `max_width`: вычислять `cache_key_mw` от **запрошенного** `path` (не resolved) и проверять кэш ДО `resolve_existing_media_storage_key` (которая ходит в R2). При промахе — текущая логика.
2. gunicorn: `--worker-class gthread --threads 8 --timeout 60` (WORKERS оставить из env).
3. В `docker-entrypoint.sh` удалить `manage.py clear_cache` (вайпит кэш ресайзов при каждом деплое). НЕ трогать остальной скрипт.

**Проверка:** два подряд запроса `curl -so /dev/null -w '%{time_total}\n' "http://localhost:8000/api/catalog/proxy-media?path=<существующий>&max_width=400"` — второй заметно быстрее; контейнер бэкенда поднимается и health-check зелёный.

## Этап 8 (P1): nginx — прямой маршрут /media и кэш proxy-media

**Файл:** `nginx/default.conf`.

**Сделать:**
1. Добавить `location /media/ { proxy_pass http://backend:8000; ... стандартные proxy_set_header ...; expires 30d; }` — убрать двойной прокси через Next.
2. Добавить `proxy_cache` зону для `location /api/catalog/proxy-media` (key с учётом query, valid 200 30d, размер 1g).

**Проверка:** конфиг валиден (`nginx -t` в контейнере), картинка по `/media/...` открывается, повторный запрос proxy-media отдаётся с `X-Cache-Status: HIT` (добавить заголовок в конфиг).

## Этап 9 (P2): JSON-LD карточки — рейтинг и полнота Offer

**Файл:** `frontend/src/pages/product/[[...slug]].tsx` (productSchema, ~1302).

**Сделать:** если у товара есть отзывы/рейтинг в payload (исследовать поля API: grep `rating|reviews_count` в сериализаторах) — добавить `aggregateRating`. В `Offer` добавить `priceValidUntil` (+30 дней) и `itemCondition: 'https://schema.org/NewCondition'`. Если рейтинга в API нет — добавить только Offer-поля и зафиксировать в отчёте, что aggregateRating требует доработки API.

**Проверка:** HTML карточки → JSON-LD валиден (вставить в https://validator.schema.org вручную либо распарсить `JSON.parse` в node-скрипте).

## Этап 10 (P2): CI

**Создать** `.github/workflows/ci.yml`: два джоба.
- backend: python 3.12, `poetry install`, `flake8`, `pytest` (с сервисами postgres+redis).
- frontend: node 20, `npm ci`, `npm run lint`, `tsc --noEmit`, `npm run build`.
Триггер: PR и push в main.

**Проверка:** запушить ветку, убедиться что workflow стартует и оба джоба зелёные (если тесты падают по причинам вне ТЗ — зафиксировать список падений в отчёте, не чинить молча).

---

## Общие требования

1. **Ветки:** `seo/p0-locale-redirects` (этапы 1–3), `seo/p1-sitemap-cache` (4–5), `perf/p1-resolve-media` (6–8), `seo/p2-jsonld` (9), `ci/github-actions` (10). Коммиты на русском, формат «SEO: …» / «Перформанс: …», без Co-Authored-By.
2. **Не делать:** рефакторинг соседнего кода, переименования, форматирование, обновление зависимостей, изменение текстов/переводов, удаление «мёртвого» кода вне явно указанного.
3. **Отчёт по каждому этапу:** что изменено (файлы:строки), как проверено (команды и вывод), что требует ручных действий владельца (Cloudflare Cache Rules, Search Console).
4. После всех этапов: запросить переобход в Search Console (вручную владельцем) — главная, категории, 10 карточек обеих локалей; отправить sitemap заново.
