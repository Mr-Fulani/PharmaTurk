# AI модуль: быстрый тест после запуска

После `./restart.sh --fast --logs` (или полного рестарта) контейнеры подняты. Ниже — что сделать по шагам.

---

## Минимальный чеклист: как потестить всё по порядку

| # | Что сделать | Команда / действие |
|---|-------------|--------------------|
| 0 | Поднять проект | `./restart.sh --fast --logs` (или `docker compose up -d`) |
| 1 | RAG (один раз) | `docker compose exec backend poetry run python manage.py setup_ai_rag` |
| 2 | Прогон по 2 товарам (синхронно, без очереди) | `docker compose exec backend poetry run python manage.py benchmark_ai 2` |
| 3 | Посмотреть результат в админке | http://localhost:8000/admin/ → **AI** → **Логи AI обработки** |
| 4 | (Опционально) Запуск через API в очередь | Получить JWT (`POST /api/auth/jwt/create/`), затем `POST /api/ai/process/<id>/`; смотреть логи `celery_ai`. |

**Быстрый прогон без очереди:** шаги 1 + 2 выполняются в контейнере `backend`, воркер `celery_ai` для benchmark не нужен (он нужен только для задач, поставленных через API). В конце `benchmark_ai` в консоли будет сводка: успех/ошибки, cost_usd, средняя уверенность.

---

## 1. Подготовка RAG (один раз или после смены категорий/шаблонов)

В отдельном терминале (контейнеры должны быть запущены):

```bash
# Создать коллекции Qdrant и загрузить категории + шаблоны
docker compose exec backend poetry run python manage.py setup_ai_rag
```

Если категорий много, команда может занять минуту (эмбеддинги через OpenAI). Без `OPENAI_API_KEY` в `.env` упадёт с ошибкой — ключ обязателен.

---

## 2. Проверка API AI

Backend уже отдаёт эндпоинты под префиксом `/api/ai/`. Нужна авторизация (JWT или сессия админки).

**Статистика (GET):**
```bash
# С токеном (подставьте свой JWT после логина в админке или через /api/auth/jwt/create/)
curl -s -H "Authorization: Bearer YOUR_JWT" http://localhost:8000/api/ai/stats/
# или через браузер, залогинившись в админку: http://localhost:8000/api/ai/stats/
```

**Ручной запуск обработки одного товара (POST):**
```bash
# Замените 1 на реальный ID товара из каталога
curl -X POST http://localhost:8000/api/ai/process/1/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT" \
  -d '{"generate_description": true, "categorize": true, "analyze_images": true, "auto_apply": false}'
```

Ответ: `202` и `task_id` — задача ушла в очередь `ai`. Её обрабатывает воркер **celery_ai** (если он запущен).

---

## 3. Проверка через админку Django

1. Открыть http://localhost:8000/admin/
2. Войти под суперпользователем.
3. Разделы:
   - **AI → Логи AI обработки** — список логов, фильтр по статусу, товару.
   - **AI → AI шаблоны** — шаблоны для RAG.
   - **AI → Очередь на модерацию** — записи, отправленные на модерацию (низкая уверенность и т.п.).
4. Для конкретного товара (например, из «Товары» каталога): запомнить ID, затем вручную вызвать обработку через API (см. выше) или добавить в коде/админке кнопку «Запустить AI» (если реализовано).

Логи AI: по каждой записи видно статус, сгенерированное описание, категорию, уверенность, стоимость. Действия: «Одобрить», «Отклонить», «Перезапустить AI».

---

## 4. Тест на нескольких товарах (benchmark)

В терминале:

```bash
# Сухой прогон: только показать, какие товары будут обработаны (без вызова OpenAI)
docker compose exec backend poetry run python manage.py benchmark_ai 3 --dry-run

# Реальный прогон по 3 товарам (без применения к товару)
docker compose exec backend poetry run python manage.py benchmark_ai 3

# С автоматическим применением результатов к товару
docker compose exec backend poetry run python manage.py benchmark_ai 2 --auto-apply
```

В логах контейнера **celery_ai** (или в общих логах `docker compose logs -f celery_ai`) будут сообщения о выполнении задач. Итоговая сводка (успех/ошибки, стоимость, уверенность) выводится в консоль после выполнения `benchmark_ai`.

---

## 5. Очередь Celery `ai`

Задачи из `apps.ai.tasks` маршрутизируются в очередь **ai**. Их обрабатывает только воркер **celery_ai**:

```bash
docker compose ps celery_ai
docker compose logs -f celery_ai
```

Если **celery_ai** не запущен, задачи будут копиться в Redis в очереди `ai` и не выполняться до старта воркера.

---

## 6. Типичные проблемы

| Проблема | Что проверить |
|----------|----------------|
| `setup_ai_rag` падает | `OPENAI_API_KEY` в `.env`, доступность Qdrant (`docker compose ps qdrant`). |
| Задача в очереди, но ничего не происходит | Запущен ли `celery_ai`: `docker compose ps celery_ai`. |
| Ошибка `cleanup_orphaned_media` в логах celeryworker | В настройках расписание должно указывать на задачу `catalog.cleanup_orphaned_media` (уже исправлено в конфиге). |
| 401 на `/api/ai/...` | Нужен заголовок `Authorization: Bearer <JWT>`. Получить JWT: POST `/api/auth/jwt/create/` с username/password. |

---

## Краткий чеклист первого прогона

1. ~~`docker compose exec backend poetry run python manage.py setup_ai_rag`~~ — уже сделано.
2. **Запустить тест на 1–2 товарах (синхронно, без очереди):**
   ```bash
   docker compose exec backend poetry run python manage.py benchmark_ai 2
   ```
   Обработка пойдёт прямо в контейнере; в конце будет сводка (успех/ошибки, стоимость, уверенность). Логи появятся в **AI → Логи AI обработки** в админке.
3. В админке: http://localhost:8000/admin/ → **AI** → **Логи AI обработки** — посмотреть запись, при необходимости **Одобрить** или **Отклонить**.
4. (Опционально) Запуск через очередь (нужен работающий `celery_ai`):
   - Взять ID товара из каталога.
   - `curl -X POST http://localhost:8000/api/ai/process/1/ -H "Content-Type: application/json" -H "Authorization: Bearer YOUR_JWT" -d '{}'`
   - Смотреть выполнение: `docker compose logs -f celery_ai`.

После этого можно тестировать модерацию (approve/reject), повторный запуск и пакетную обработку через API.
