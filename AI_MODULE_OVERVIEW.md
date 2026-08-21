# AI-модуль PharmaTurk: обзор

## Назначение

Модуль подготавливает контент товарной карточки: RU/EN название и описание, SEO, предложенную категорию, доменные атрибуты и, когда разрешено, анализ изображений. Каждый запуск создаёт аудируемый `AIProcessingLog` с исходными данными, результатом, токенами, расчётной стоимостью и ошибками.

Безопасный штатный сценарий — сформировать предложение с `auto_apply=False`, проверить его в Django Admin и только затем применить.

## Архитектура

```text
Явный запуск (staff API / Django Admin / management command)
                         │
                         ▼
             enqueue_product_ai_task()
       pending-лог + дедупликация постановки
                         │ after commit
                         ▼
            Celery worker очереди `ai`
                         │
                         ▼
            ContentGenerator.process_product()
             ├─ товар и контекст вариантов
             ├─ изображения → Vision (опционально)
             ├─ Qdrant RAG (best effort)
             └─ OpenAI → структурированный результат
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
      completed/moderation       auto_apply=true
       проверка сотрудником       запись в товар
```

Автоматического trigger по `Product.post_save` нет. `apps/ai/signals.py` оставлен без receiver намеренно, а парсер блокирует неявный AI-запуск во время сохранения. Для товаров сессии скрапинга сотрудник нажимает «Запустить AI» отдельно; задача ставится с `auto_apply=False`.

## Компоненты

| Компонент | Фактическая роль |
|---|---|
| `ContentGenerator` | Собирает prompt, вызывает Vision/LLM, валидирует ответ, сохраняет лог и при необходимости применяет результат. |
| `LLMClient` | Клиент OpenAI для chat completions, Vision и embeddings; считает токены и ориентировочную стоимость. |
| `QdrantManager` | Коллекции `categories` и `templates`, поиск похожего RAG-контекста. При ошибке поиск возвращает пустой контекст. |
| `R2MediaProcessor` | Получает R2 или внешние изображения, уменьшает до JPEG и передаёт base64 в Vision. |
| `AIProcessingLog` | Аудит одного запуска и его статус. |
| `AIModerationQueue` | Ручная проверка сомнительного результата. |
| `AITemplate` | Шаблоны prompt и RAG-примеры, общие либо привязанные к категории. |
| Celery `ai` | Выполняет все `apps.ai.tasks.*`, не занимая стандартную очередь. |

## Применение и модерация

`auto_apply` по умолчанию равен `false` во view, serializer, enqueue-сервисе и Celery-задаче. В этом режиме:

- качественный результат остаётся `completed` до применения сотрудником;
- сомнительный результат становится `moderation` и получает запись `AIModerationQueue`;
- действие «Проверено — применить к товару» применяет допустимые поля; обычно лог становится `approved`, но `SemanticValidator` может оставить его в `moderation`;
- reject переводит лог в `rejected`;
- reprocess создаёт принудительный повтор с `auto_apply=False`.

Факт переноса данных хранится отдельно в `application_status`: `not_applied`,
`partial`, `applied` или `failed`. Старые логи, для которых прежний интерфейс не
позволяет надёжно определить факт применения, помечаются `unknown`.

При `auto_apply=true` результат сразу проходит через `AIResultApplier`, минуя предварительную проверку `quality_checker`. `SemanticValidator` всё ещё может исключить отдельные поля и оставить лог в `moderation`, однако разрешённые поля уже будут записаны. Такой режим следует использовать только осознанно.

Проверка качества учитывает, среди прочего, confidence категории ниже `0.75`, подозрительную цену или лексику, короткое описание и семантические несоответствия.

## Варианты товара

Родительский prompt получает структурированный контекст вариантов. После успешной полной/описательной обработки:

- простые заголовки вариантов могут синхронизироваться детерминированно, без отдельного LLM-вызова;
- `prepare_variant_ai_candidates_task` сохраняет в `external_data` список вариантов, которым потенциально нужен отдельный текст;
- `process_variant_ai_task` запускается вручную и сохраняет результат варианта в его `external_data`.

Это ограничивает расход токенов для вариантов, различающихся только цветом или размером.

## Точки запуска

### Staff API

Все AI endpoints защищены `IsAdminUser`. Корректный JWT обычного пользователя недостаточен: без `is_staff=True` сервер возвращает `403`.

```bash
curl -X POST http://localhost:8000/api/auth/jwt/create/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"<staff-user>","password":"<password>"}'

curl -X POST http://localhost:8000/api/ai/process/<product-id>/ \
  -H 'Authorization: Bearer <YOUR_ACCESS_TOKEN> \
  -H 'Content-Type: application/json' \
  -d '{
    "generate_description": true,
    "categorize": true,
    "analyze_images": true,
    "use_images": true,
    "auto_apply": false
  }'
```

Ответ `202` сообщает `task_id`, `log_id` и `submitted`. Если `submitted=false`, enqueue-сервис нашёл существующий незавершённый или уже успешный лог того же типа.

`POST /api/ai/generate/` предоставляет тот же набор флагов, но принимает `product_id` в JSON и также поддерживает `processing_type`.

Image pipeline запускается только при `analyze_images=true` и `use_images=true`.
Любой из этих флагов со значением `false` запрещает загрузку изображений и
вызов Vision независимо от выбранного текстового processing mode.

### Django Admin

- Товары: полная обработка без применения или явная обработка с авто-применением.
- Сессии/задачи скрапинга: отдельная кнопка запуска для созданных/обновлённых товаров, всегда без авто-применения.
- AI → Логи: просмотр, применение, отклонение и принудительный повтор.
- AI → Очередь модерации: назначение и resolve.
- `/admin/ai/manual-tasks/`: массовые ручные задачи, способные расходовать OpenAI-токены.

### Синхронный benchmark

```bash
docker compose exec backend poetry run python manage.py benchmark_ai 5 --dry-run
docker compose exec backend poetry run python manage.py benchmark_ai 3
docker compose exec backend poetry run python manage.py benchmark_ai 2 --auto-apply
```

`--dry-run` только выводит выбранные ID. Остальные варианты выполняют pipeline внутри процесса команды и не требуют worker, но требуют БД и OpenAI; Qdrant нужен для полноценного RAG.

## Подготовка RAG

```bash
docker compose exec backend poetry run python manage.py setup_ai_rag
```

Команда последовательно выполняет `init_qdrant`, `sync_categories` и `import_templates`. Embeddings создаются через OpenAI, поэтому нужны `OPENAI_API_KEY`, доступ к Qdrant и согласованная размерность embedding-модели. После существенного изменения категорий или шаблонов синхронизацию нужно повторить.

## Что запускается по расписанию

Токенозатратные AI-задачи `process_uncategorized`, `process_without_description` и `retry_failed_processing` в Celery Beat отключены и доступны только вручную. В Beat остаётся только `cleanup_old_ai_logs` раз в неделю; она удаляет `completed`/`approved` логи старше 30 дней и OpenAI не вызывает.

Полный перечень расписаний и очередей описан в `CELERY_TASKS.md`.

## Сильные стороны

- видимый pending-лог создаётся до отправки в брокер;
- постановка защищена от повторного клика и выполняется после DB commit;
- модерация включена по умолчанию;
- AI, рекомендации и стандартные фоновые задачи разведены по очередям;
- Qdrant используется как best-effort enhancement, а не единая точка отказа;
- простые варианты не требуют отдельного LLM-вызова.

## Ограничения и риски

- качество LLM не гарантировано, особенно при слабых исходных данных;
- `auto_apply=true` переносит риск прямо в каталог;
- OpenAI, Redis и worker `ai` обязательны для асинхронного pipeline;
- сумма `cost_usd` ориентировочная: тарифы зашиты в клиент и требуют ручного обновления;
- RAG-индекс не синхронизируется после каждого изменения модели автоматически;
- AI и visual search используют общий hardened image fetcher: DNS/IP и redirect
  проверяются на каждом переходе, загрузка и число пикселей ограничены, а R2
  читается напрямую с bounded-read;
- флаги AI в `ScraperConfig` пока не являются автоматическим trigger.
