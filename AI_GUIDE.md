# AI-модуль PharmaTurk

AI-модуль формирует описание и SEO, предлагает категорию, извлекает атрибуты и при необходимости анализирует изображения товара. По умолчанию результат сохраняется в журнале для проверки и **не применяется к товару автоматически**.

Актуальные источники правды в коде:

- `backend/apps/ai/views.py` и `serializers.py` — API и его входные данные;
- `backend/apps/ai/tasks.py` — постановка и выполнение Celery-задач;
- `backend/apps/ai/services/content_generator.py` — основной pipeline;
- `backend/apps/ai/signals.py` — политика автоматического запуска;
- `backend/config/settings.py` — очереди и расписание.

## 1. Как запускается обработка

Автоматического запуска после сохранения товара или завершения парсинга сейчас нет. Файл `apps/ai/signals.py` намеренно не регистрирует `post_save` receiver, чтобы обычное сохранение товара не расходовало токены OpenAI. Поля `ai_on_create_enabled` и `ai_on_update_enabled` в конфигурации скрапера сами по себе задачу не ставят.

Поддерживаются явные способы запуска:

1. action для выбранных товаров в Django Admin;
2. кнопка или action «Запустить AI» для сессии/задачи парсинга;
3. staff-only API;
4. management-команда `benchmark_ai` для синхронной диагностики;
5. страница `/admin/ai/manual-tasks/` для массовых ручных задач.

Все штатные точки запуска используют `auto_apply=False`, кроме явно названного admin action «Полная AI обработка + авто-применение», параметра `--auto-apply` у benchmark и API-запроса с `"auto_apply": true`.

## 2. Поток данных

1. `enqueue_product_ai_task()` блокирует строку товара, проверяет существующие активные/готовые логи и создаёт `AIProcessingLog` со статусом `pending`.
2. После commit в очередь `ai` отправляется `process_product_ai_task`.
3. `ContentGenerator` собирает данные товара и контекст вариантов.
4. Если изображения разрешены, до пяти изображений оптимизируются и могут быть отправлены в Vision API.
5. Qdrant, если доступен и заполнен, добавляет к prompt похожие категории и шаблоны. При ошибке Qdrant pipeline продолжает работу без RAG-контекста.
6. OpenAI возвращает структурированный результат; журнал сохраняет ответ, токены, расчётную стоимость и время обработки.
7. При `auto_apply=False` результат получает статус `completed` либо `moderation`. При `auto_apply=True` результат сразу применяется; ошибка применения переводит лог в `failed`.
8. После полной обработки синхронизируются простые названия вариантов, формируется список вариантов-кандидатов на отдельную ручную AI-обработку и откладывается переиндексация товара для рекомендаций.

Повторный обычный запуск не создаёт дубликат, если для того же товара и типа уже есть `pending`, `processing`, `completed`, `moderation` или `approved` лог. Принудительный повтор (`force=True`) используется в действиях перезапуска.

## 3. Данные и компоненты

### Модели

- `AIProcessingLog` — входные данные, результат, метрики, ошибки и статусы `pending`, `processing`, `completed`, `moderation`, `approved`, `rejected`, `failed`;
- `AIModerationQueue` — причина, приоритет, назначенный сотрудник и время разрешения;
- `AITemplate` — активные prompt/RAG-шаблоны типов `description`, `category_example`, `attribute_extraction`, `image_prompt`, `category_instruction`.

### Сервисы

- `ContentGenerator` — оркестрация pipeline и применение результата;
- `LLMClient` — OpenAI chat, Vision и embeddings;
- `R2MediaProcessor` — получение и уменьшение изображений перед Vision;
- `QdrantManager` — коллекции `categories` и `templates`, поиск RAG-контекста;
- `AIResultApplier` — перенос одобренных полей в базовый и доменный товар;
- `quality_checker` и `SemanticValidator` — решение о ручной модерации.

R2 опционален для основного хранилища проекта. AI-процессор также умеет читать внешние URL изображений. Наличие доступного изображения не гарантирует анализ: это зависит от режима товара и параметров запуска.

### Модерация

Без авто-применения ручная проверка включается, например, при confidence категории ниже `0.75`, подозрительной цене/лексике, слишком коротком описании или семантическом несоответствии. Сотрудник может применить, отклонить или принудительно перезапустить результат.

`auto_apply=True` пропускает предварительное решение `quality_checker` и сразу применяет поля, не отклонённые `SemanticValidator`. Семантические проблемы всё ещё могут оставить лог в `moderation`, но часть данных к этому моменту уже будет записана в товар. Поэтому режим подходит только для контролируемых запусков.

## 4. API

Все `/api/ai/...` endpoints имеют permission `IsAdminUser`: пользователь должен быть аутентифицирован и иметь `is_staff=True`. Обычный пользователь с корректным JWT получает `403`; анонимный запрос — `401`.

### Обработка товара по ID

```http
POST /api/ai/process/<product_id>/
```

```json
{
  "generate_description": true,
  "categorize": true,
  "analyze_images": true,
  "use_images": true,
  "auto_apply": false
}
```

Все пять полей необязательны и имеют показанные значения по умолчанию.

- `generate_description` — включить текстовую генерацию;
- `categorize` — включить предложение категории;
- `analyze_images` — участвует в выборе режима обработки;
- `use_images` — разрешает фактическую загрузку изображений;
- `auto_apply` — сразу применить результат к товару.

Vision и загрузка изображений выполняются только когда оба флага истинны.
Поэтому любой из `"analyze_images": false` или `"use_images": false` полностью
отключает image pipeline; для явности в примерах без Vision допустимо передать
оба значения `false`.

Пример для staff-пользователя:

```bash
curl -X POST http://localhost:8000/api/auth/jwt/create/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"<staff-user>","password":"<password>"}'

curl -X POST http://localhost:8000/api/ai/process/<product-id>/ \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <access-token>' \
  -d '{"generate_description":true,"categorize":true,"analyze_images":true,"use_images":true,"auto_apply":false}'
```

Успешная постановка возвращает `202`, `task_id`, `log_id` и `submitted`. Значение `submitted=false` означает, что подходящий лог уже существовал и новая задача не создавалась.

### Альтернативный endpoint

```http
POST /api/ai/generate/
```

Он принимает те же флаги, а также обязательный `product_id` и необязательный `processing_type`: `full`, `description_only`, `categorization_only` или `image_analysis`.

### Просмотр и модерация

- `GET /api/ai/logs/` — список логов;
- `POST /api/ai/logs/<id>/approve/` — применить завершённый результат;
- `POST /api/ai/logs/<id>/reject/` — отклонить;
- `POST /api/ai/logs/<id>/reprocess/` — принудительный повтор без авто-применения;
- `/api/ai/moderation/` — очередь модерации;
- `/api/ai/templates/` — шаблоны;
- `GET /api/ai/stats/?days=30` — статистика, диапазон `1..365` дней.

## 5. Django Admin

Для товаров доступны действия:

- «Полная AI обработка (без авто-применения)»;
- «Полная AI обработка + авто-применение»;
- просмотр последнего AI-статуса.

В админке скрапера кнопка сессии/задачи выбирает товары из `ScrapedProductLog` с action `created` или `updated` и ставит их в очередь с `auto_apply=False`. Это отдельное действие и не является продолжением парсинга.

Раздел AI позволяет просматривать и редактировать логи, применять результат, принудительно повторять обработку и управлять очередью модерации. Страница `/admin/ai/manual-tasks/` запускает категоризацию товаров без категории, генерацию отсутствующих описаний, повтор недавних ошибок и очистку логов. Первые три действия могут расходовать токены и не включены в Celery Beat.

## 6. Команды диагностики

Подготовка RAG создаёт коллекции Qdrant, синхронизирует категории и импортирует шаблоны:

```bash
docker compose exec backend poetry run python manage.py setup_ai_rag
```

Синхронный benchmark не использует очередь Celery:

```bash
# Только показать выбранные товары; OpenAI не вызывается
docker compose exec backend poetry run python manage.py benchmark_ai 3 --dry-run

# Реальная обработка без применения результата
docker compose exec backend poetry run python manage.py benchmark_ai 3

# Реальная обработка с немедленным применением
docker compose exec backend poetry run python manage.py benchmark_ai 3 --auto-apply
```

Команда выбирает первые `N` товаров из `Product`; это smoke/стоимостной benchmark, а не изолированный unit-тест. Реальные запуски требуют доступных PostgreSQL, OpenAI и, для RAG, Qdrant. Асинхронный API дополнительно требует Redis и worker очереди `ai`.

## 7. Конфигурация

```dotenv
OPENAI_API_KEY=
AI_MODEL=gpt-4o-mini
AI_VISION_MODEL=gpt-4o-mini
AI_EMBEDDING_MODEL=text-embedding-3-small

QDRANT_HOST=qdrant
QDRANT_PORT=6333

# Опционально для Cloudflare R2
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=
R2_PUBLIC_URL=
```

При смене embedding-модели нужно учитывать, что `QdrantManager` сейчас создаёт векторы размерности `1536`. При изменении размерности коллекции необходимо пересоздать согласованно с моделью и повторно выполнить `setup_ai_rag`.

## 8. Ограничения

- AI зависит от внешнего OpenAI API и может расходовать заметный бюджет; расчёт `cost_usd` основан на статической таблице цен в коде и может отличаться от фактического счёта.
- Qdrant улучшает контекст, но его недоступность не всегда делает задачу ошибочной: генерация может продолжиться без RAG.
- Модель может ошибаться или придумать неподтверждённый атрибут; рекомендуемый режим — `auto_apply=False` и модерация.
- Шаблоны и категории в Qdrant не обновляются автоматически после каждого изменения БД; RAG нужно синхронизировать явно.
- Отдельная AI-обработка содержательных вариантов запускается вручную; обычные цветовые варианты не должны автоматически умножать число LLM-вызовов.
