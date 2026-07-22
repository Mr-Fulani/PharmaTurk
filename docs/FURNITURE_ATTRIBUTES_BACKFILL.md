# Backfill характеристик мебели

Команда `backfill_furniture_attributes` создаёт локализованные динамические
характеристики для уже существующих записей `FurnitureProduct`. Она нужна после
изменений правил нормализации мебели или после импорта товаров, у которых
характеристики остались только в исходных полях.

Команда идемпотентна: безопасный повторный запуск без `--overwrite` не меняет
уже существующие значения.

## Базовая production-команда

Все примеры ниже выполняются из корня проекта на сервере:

```bash
docker compose -p mudaroba \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  exec -T backend \
  poetry run python manage.py backfill_furniture_attributes <флаги>
```

Перед применением данных обязательно выполните dry-run:

```bash
docker compose -p mudaroba \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  exec -T backend \
  poetry run python manage.py backfill_furniture_attributes
```

После проверки результата выполните безопасное применение:

```bash
docker compose -p mudaroba \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  exec -T backend \
  poetry run python manage.py backfill_furniture_attributes --apply
```

## Флаги

| Флаг | По умолчанию | Назначение |
|---|---:|---|
| `--apply` | выключен | Записывает изменения. Без флага команда работает в режиме dry-run. |
| `--overwrite` | выключен | Перезаписывает существующие значения нормализованными. Разрешён только вместе с `--apply`. |
| `--audit-titles` | выключен | Проверяет соответствие текущих заголовков категориям. Заголовки не изменяет. |
| `--batch-size N` | `200` | Число товаров в одной транзакции. После каждого пакета выводится строка прогресса. |
| `--start-pk N` | `0` | Начинает с товара с PK `N` включительно. Используется для продолжения прерванного запуска. |
| `--limit N` | `0` | Обрабатывает не более `N` товаров. Значение `0` означает отсутствие ограничения. |

Некорректные значения `--batch-size 0`, отрицательные `--start-pk`/`--limit`
и `--overwrite` без `--apply` завершают команду до изменения данных.

## Рекомендуемый порядок запуска

### 1. Проверка небольшого диапазона

```bash
docker compose -p mudaroba \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  exec -T backend \
  poetry run python manage.py backfill_furniture_attributes \
  --limit 100 \
  --batch-size 50
```

В dry-run поле `changed` всегда равно `0`. Поле `candidates` показывает число
нормализованных значений, которые команда смогла построить из исходных данных.

### 2. Безопасное применение ко всему каталогу

```bash
docker compose -p mudaroba \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  exec -T backend \
  poetry run python manage.py backfill_furniture_attributes \
  --apply \
  --batch-size 200
```

Без `--overwrite` существующие значения, включая отредактированные вручную,
сохраняются.

### 3. Отдельный аудит заголовков

```bash
docker compose -p mudaroba \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  exec -T backend \
  poetry run python manage.py backfill_furniture_attributes \
  --audit-titles \
  --batch-size 200
```

Аудит выводит строки вида:

```text
TITLE_MISMATCH product=123 category=bed-bases name=Кровать TONSTAD
```

Это только отчёт. Команда не исправляет заголовок и не переносит товар в другую
категорию. Категории, переводы, дерево родителей и семантические политики
загружаются один раз, поэтому аудит не создаёт запрос всех категорий для каждого
товара.

Аудит можно совместить с применением:

```bash
docker compose -p mudaroba \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  exec -T backend \
  poetry run python manage.py backfill_furniture_attributes \
  --apply \
  --audit-titles
```

Для production предпочтительнее запускать аудит отдельно: его вывод проще
проверять, а запись характеристик завершается быстрее.

## Продолжение прерванного запуска

После каждого успешно завершённого пакета команда выводит:

```text
PROGRESS: last_pk=12000 scanned=800 candidates=3150 changed=3012 title_mismatches=0 resume_start_pk=12001
```

Пакет записывается в отдельной транзакции. Строка `PROGRESS` появляется после
её успешного завершения. Для продолжения используйте значение
`resume_start_pk`:

```bash
docker compose -p mudaroba \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  exec -T backend \
  poetry run python manage.py backfill_furniture_attributes \
  --apply \
  --start-pk 12001 \
  --batch-size 200
```

`--start-pk` включительный. Если у вас известен только последний успешно
обработанный PK, передайте следующий PK или значение `resume_start_pk` из лога.

Если процесс оборвался до следующей строки `PROGRESS`, соответствующий пакет
откатывается. Повторный запуск безопасен благодаря идемпотентности.

## Ограниченный диапазон

Обработать максимум 500 товаров начиная с PK 10000:

```bash
docker compose -p mudaroba \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  exec -T backend \
  poetry run python manage.py backfill_furniture_attributes \
  --apply \
  --start-pk 10000 \
  --limit 500 \
  --batch-size 100
```

`--limit` применяется после `--start-pk`.

## Опасный режим overwrite

```bash
docker compose -p mudaroba \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  exec -T backend \
  poetry run python manage.py backfill_furniture_attributes \
  --apply \
  --overwrite \
  --limit 100
```

`--overwrite` заменяет существующие динамические характеристики значениями,
построенными из исходных полей товара. В том числе могут быть потеряны ручные
правки администратора.

Используйте этот режим только если:

1. выполнен dry-run на том же диапазоне;
2. проверена резервная копия PostgreSQL;
3. ручные значения действительно требуется заменить;
4. сначала выполнен ограниченный запуск через `--limit`.

Для обычного деплоя `--overwrite` не нужен.

## Настройка batch-size

- `200` — рекомендуемое production-значение;
- `50–100` — если сервер ограничен по памяти или нужен более частый прогресс;
- `500` — допустимо на сервере с достаточной памятью и быстрой PostgreSQL;
- слишком большое значение увеличивает размер транзакции и объём отката при
  прерывании.

Команда читает товары через Django `iterator`, загружает существующие значения
один раз на пакет и записывает новые значения через `bulk_create`/`bulk_update`.

## Проверка результата

Повторите безопасный запуск:

```bash
docker compose -p mudaroba \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  exec -T backend \
  poetry run python manage.py backfill_furniture_attributes --apply
```

Для полностью обработанного каталога итог должен содержать `changed=0`.

Пример финальной строки:

```text
APPLY: scanned=2064 candidates=8818 changed=0 title_mismatches=0 audit_titles=false last_pk=2064
```

Значения полей:

- `scanned` — количество просмотренных товаров;
- `candidates` — количество распознанных значений в исходных данных;
- `changed` — количество созданных или перезаписанных записей;
- `title_mismatches` — число подозрительных заголовков; заполняется только с
  `--audit-titles`;
- `last_pk` — последний просмотренный PK, либо `0`, если выборка пуста.

## Что запускать не нужно

- `seed_catalog_data` для этого backfill не требуется;
- `makemigrations` запускать на production нельзя;
- `--overwrite` не является частью обычного деплоя;
- повторная индексация Qdrant этим backfill не требуется.
