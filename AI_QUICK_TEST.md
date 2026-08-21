# AI-модуль: быстрый smoke-тест

Эта инструкция может выполнять реальные запросы OpenAI и расходовать quota; исключение — шаги, явно помеченные как dry-run. Запускайте её только на тестовых товарах и оставляйте `auto_apply=false`, пока результат не проверен.

Команды ниже приведены для Docker Compose. Если стек уже занят или недоступен, не запускайте второй экземпляр поверх него: выполните только статические/unit-проверки либо дождитесь доступного тестового окружения.

## Предусловия

Нужны:

- PostgreSQL, Redis и Qdrant;
- backend и worker `celery_ai` для асинхронного API-теста;
- `OPENAI_API_KEY`;
- хотя бы один товар;
- Django-пользователь с `is_staff=True` и его JWT.

AI API защищён `IsAdminUser`. Обычный аутентифицированный пользователь получает `403`, даже если JWT корректен. Анонимный запрос получает `401`.

Проверить сервисы без изменения данных:

```bash
docker compose ps backend redis qdrant celery_ai
docker compose logs --tail=100 celery_ai
```

## 1. Безопасная проверка выбора товаров

`--dry-run` не вызывает OpenAI и не создаёт AI-лог:

```bash
docker compose exec backend poetry run python manage.py benchmark_ai 2 --dry-run
```

Ожидается список ID либо сообщение, что товаров нет.

## 2. Подготовка RAG

Выполняйте при первом развёртывании и после существенного изменения категорий или AI-шаблонов:

```bash
docker compose exec backend poetry run python manage.py setup_ai_rag
```

Команда создаёт коллекции `categories` и `templates`, затем записывает embeddings категорий и шаблонов. Она расходует OpenAI embeddings. Просмотрите весь вывод: отдельные команды выводят warnings и могут пропустить конкретные записи, поэтому финальная строка сама по себе не доказывает полноту индекса.

## 3. Синхронный тест одного товара

```bash
docker compose exec backend poetry run python manage.py benchmark_ai 1
```

Этот путь вызывает `ContentGenerator` прямо внутри management-команды:

- worker `celery_ai` ему не нужен;
- OpenAI и база нужны;
- Qdrant нужен для полноценного RAG, но pipeline может продолжить работу без RAG;
- результат не применяется к товару, потому что `--auto-apply` не указан.

Если для выбранного товара уже есть успешный лог того же типа, сервис может вернуть его без нового LLM-вызова. Benchmark не устанавливает `force=True`.

Проверьте итоговый статус, confidence и `cost_usd`, затем откройте Django Admin → AI → Логи AI обработки. Статус может быть `completed` или `moderation`; `failed` требует проверки `error_message` и traceback лога.

`--auto-apply` в smoke-тесте не используйте, пока результат не проверен. Этот флаг сразу изменяет товар.

## 4. Получение staff JWT

Получите access token от staff-пользователя:

```bash
curl -i -X POST http://localhost:8000/api/auth/jwt/create/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"<staff-user>","password":"<password>"}'
```

Скопируйте поле `access` из ответа. Вход обычного пользователя тоже выдаёт JWT, но вызов `/api/ai/...` с ним корректно завершится `403 Forbidden`.

## 5. Асинхронный API-тест

Получить существующий ID можно без предположений о конкретной базе:

```bash
docker compose exec backend poetry run python manage.py shell -c \
  "from apps.catalog.models import Product; print(Product.objects.values_list('id', flat=True).first())"
```

Поставьте обработку в очередь:

```bash
curl -i -X POST http://localhost:8000/api/ai/process/<product-id>/ \
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

Ожидаемый HTTP status — `202 Accepted`. В JSON должны быть:

- `task_id` — идентификатор Celery-задачи;
- `log_id` — заранее созданный `pending`-лог;
- `submitted` — была ли создана новая задача;
- `status: "queued"`.

`submitted=false` не является ошибкой: enqueue-сервис нашёл существующий активный или готовый лог того же типа и не продублировал расход.

Наблюдение за worker:

```bash
docker compose logs -f --tail=100 celery_ai
```

После завершения запросите конкретный лог:

```bash
curl -i \
  -H 'Authorization: Bearer <YOUR_ACCESS_TOKEN> \
  http://localhost:8000/api/ai/logs/<log-id>/
```

Для проверки без Vision достаточно выключить любой из двух флагов; в примере
оба выключены для явности:

```json
{
  "generate_description": true,
  "categorize": true,
  "analyze_images": false,
  "use_images": false,
  "auto_apply": false
}
```

`use_images=false` — фактический запрет загрузки изображений. Одного `analyze_images=false` недостаточно, когда описание и категоризация оставляют обработку в режиме `full`.

## 6. Проверка permissions

Минимальная матрица ожидаемого поведения для любого `/api/ai/...` endpoint:

| Клиент | Ожидаемый ответ |
|---|---|
| Без токена | `401 Unauthorized` |
| JWT обычного пользователя (`is_staff=False`) | `403 Forbidden` |
| JWT staff-пользователя | запрос допускается; далее status зависит от данных |

Проверка статистики staff-токеном:

```bash
curl -i \
  -H 'Authorization: Bearer <YOUR_ACCESS_TOKEN> \
  'http://localhost:8000/api/ai/stats/?days=30'
```

`days` должен быть целым числом от `1` до `365`.

## 7. Проверка модерации и применения

В Django Admin:

1. откройте AI → Логи AI обработки;
2. проверьте сгенерированные RU/EN поля, категорию, атрибуты, исходные данные и стоимость;
3. если статус `moderation`, откройте связанную очередь и причину;
4. применяйте проверенный лог единым action «Проверено — применить к товару»; предварительно менять статус не нужно;
5. проверьте `application_status`: `applied` означает полное применение, `partial` — безопасные поля применены, но очередь остаётся открытой;
6. для повторного прогона используйте reprocess/rerun — он ставит `force=True`, но сохраняет `auto_apply=False`.

Кнопки «Запустить AI» в сессиях и задачах скрапинга являются ручными. После обычного парсинга AI автоматически не стартует.

## 8. Быстрые unit-проверки без Docker

Если зависимости уже установлены локально, permissions и валидацию API можно проверить без внешних OpenAI/Qdrant вызовов:

```bash
cd backend
poetry run pytest \
  apps/ai/tests/test_api_permissions.py \
  apps/ai/tests/test_api_validation.py \
  apps/ai/tests/test_queueing.py
```

`test_queueing.py` использует Django DB и может требовать настроенное тестовое подключение PostgreSQL. Первые два файла проверяют permissions/serializers с mock и не являются end-to-end проверкой инфраструктуры.

## Диагностика

| Симптом | Проверка |
|---|---|
| `401` | Передан ли `Authorization: Bearer <YOUR_ACCESS_TOKEN> не истёк ли токен. |
| `403` | У пользователя должен быть `is_staff=True`; обычного JWT недостаточно. |
| `202`, но лог остаётся `pending` | Работают ли Redis и `celery_ai`, попала ли задача в очередь `ai`. |
| `submitted=false` | Уже существует лог подходящего типа; для осознанного повторного запуска используйте admin reprocess. |
| Ошибка OpenAI | Проверьте ключ, quota, сетевой доступ и `error_message` в AI-логе. |
| RAG пустой | Проверьте Qdrant и вывод `setup_ai_rag`; pipeline может завершиться без RAG. |
| Изображения не проанализированы | Проверьте `use_images`, наличие URL и `input_data.image_urls_failed` в логе. |
| Товар неожиданно изменился | Проверьте, не использовался ли `auto_apply=true` или admin action с авто-применением. |
