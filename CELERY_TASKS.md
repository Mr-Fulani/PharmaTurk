# Celery Beat: задачи по расписанию

Список задач, которые **не тратят токены OpenAI**. AI-задачи (категоризация, описания, повтор неудачных) только вручную — `/admin/ai/manual-tasks/`.

---

## Задачи в работе

### currency-update-rates
**Расписание:** каждые 4 часа

**Что делает:** Обновление курсов валют из внешнего источника (API). Сохраняет в `CurrencyRate`.

**Текущее состояние:** Работает. Использует `CurrencyRateService`.

---

### currency-update-prices
**Расписание:** раз в день

**Что делает:** Пересчитывает цены товаров по актуальным курсам валют. Обходит товары батчами (batch_size=200).

**Текущее состояние:** Работает. Вызывает management-команду `update_product_prices`.

---

### cleanup-scraper-sessions
**Расписание:** раз в неделю

**Что делает:** Удаляет старые сессии парсинга (`ScrapingSession`) и логи (`ScrapedProductLog`) старше 30 дней.

**Текущее состояние:** Работает. Освобождает БД от старых логов парсинга.

**Что нужно:** Решить — оставить 30 дней или изменить срок хранения.

---

### cleanup-orphaned-media
**Расписание:** раз в день

**Что делает:** Удаляет файлы из R2/локального хранилища, на которые нет ссылок в БД. Исключает защищённые пути (AI, temp).

**Текущее состояние:** Работает. Экономит место в storage.

**Что нужно:** Решить — оставить или отключить (если не используете R2/медиа).

---

### ai-cleanup-old-logs
**Расписание:** раз в неделю

**Что делает:** Удаляет завершённые/одобренные логи AI (`AIProcessingLog`) старше месяца (30 дней).

**Текущее состояние:** Работает. Не тратит токены. Можно также запускать вручную в `/admin/ai/manual-tasks/` с нужным количеством дней.

---

### recsys-sync-all
**Расписание:** раз в 3 дня

**Что делает:** Полная переиндексация векторов товаров в Qdrant. Использует локальные модели: SentenceTransformer (текст) и CLIP (изображения). Без OpenAI.

**Текущее состояние:** Работает. Нужна для рекомендаций «похожие товары», «дополнить образ» и т.п.

**Ручной запуск (все товары):**
```bash
# Docker (Poetry)
docker compose exec backend poetry run python manage.py sync_product_vectors --full

# или частями (backend 1.5g — OOM при загрузке CLIP; использовать celeryworker 2g):
docker compose exec celeryworker poetry run python manage.py sync_product_vectors --batch 50
# до конца: --until-done (повторяет батчи пока remaining > 0)
docker compose exec celeryworker poetry run python manage.py sync_product_vectors --until-done
# при рассинхроне (No vector found): --force --until-done (сброс last_synced, полная переиндексация)
docker compose exec celeryworker poetry run python manage.py sync_product_vectors --force --until-done
# конкретный товар: --product-id 946 --product-id 947

# После переиндексации — если похожие не показываются, очистить кэш:
docker compose exec backend poetry run python manage.py clear_similar_cache

# Локально (из backend/)
poetry run python manage.py sync_product_vectors --full
```
Полная синхронизация идёт в Celery в фоне. Прогресс — в логах celeryworker.

**Процедура при «No vector found» или пустых похожих:**
1. `sync_product_vectors --force --until-done` (сбрасывает last_synced, переиндексирует всё; кэш очищается автоматически)
2. Для конкретных товаров: `sync_product_vectors --product-id X --product-id Y` (обходит is_available)
3. Если похожие всё ещё пустые: `clear_similar_cache` (теперь удаляет все rec:similar:* по паттерну Redis)

Проблема только в recsys: sync_product_vectors и clear_similar_cache. Другие задачи (currency, scrapers, ai-cleanup) не используют Qdrant/векторы.

---

## Отключённые задачи

### find-merge-duplicates
**Статус:** Только ручной запуск — убрано из расписания.

**Что делает:** Ищет дубликаты товаров между API-товарами и распарсенными. Группирует по точному совпадению названий (lowercase, strip). Объединяет только когда есть и API, и распарсенные товары с одинаковым названием — оставляет основной API-товар, привязывает к нему распарсенные.

**Ручной запуск:** Массовое действие «Поиск и объединение дубликатов» в админке на страницах товаров (любой тип). Выберите товары → действие → применить. **Задача всегда выполняется по всему каталогу** — выбор не влияет. Требует `mem_limit: 2g` для celeryworker.

**Как включить в расписание:** Раскомментировать блок в `backend/config/settings.py` → `CELERY_BEAT_SCHEDULE`.

---

### refresh-stock, run-all-scrapers
**Статус:** Отключено — доработаем после парсеров.

**Что делают:**
- `refresh-stock` — проверка наличия товаров на складе/у поставщиков (каждые 2 ч). Сейчас заглушка — логики нет.
- `run-all-scrapers` — запуск всех активных парсеров (каждые 12 ч). Работает, но временно выключен.

**Как включить:** Раскомментировать блоки в `backend/config/settings.py` → `CELERY_BEAT_SCHEDULE`.

---

### VAPI (vapi-sync-products, vapi-sync-categories, vapi-full-sync)
**Статус:** Отключено — фича не используется.

**Что делают:**
- `vapi-sync-products` — подтягивает товары из VAPI API (каждые 6 ч)
- `vapi-sync-categories` — синхронизирует категории и бренды (раз в день)
- `vapi-full-sync` — полная синхронизация каталога (раз в 3 дня)

**Как включить:** Раскомментировать блок в `backend/config/settings.py` → `CELERY_BEAT_SCHEDULE`. Указать `VAPI_BASE_URL` и `VAPI_API_KEY` в `.env`.

---

## Дополнительные задачи (не в Beat)

- `currency.cleanup_old_logs` — очистка старых логов курсов (можно добавить в расписание)
- `currency.health_check` — проверка здоровья системы валют
- `index_product_vectors` — индексация одного/нескольких товаров (вызывается при сохранении товара или через `sync_all_products_to_qdrant`)
