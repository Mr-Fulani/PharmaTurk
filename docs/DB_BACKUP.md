# Бэкап базы во внешнее хранилище

Проверено: 2026-10-19. Код: `backend/apps/monitoring/db_backup.py`, задачи
`run_database_backup` и `check_database_backup` в `apps/monitoring/tasks.py`.

## Простыми словами

Каждую ночь сервер делает полную копию базы (товары, заказы, пользователи) и
отправляет её в отдельное хранилище Cloudflare R2 — не на тот же диск. Если
сервер Hetzner сгорит или диск откажет, базу можно поднять на новом сервере из
последней копии (инструкция ниже).

- Хранится 14 копий: за последние 7 дней, последние 4 недели и 3 месяца.
  Старые удаляются сами.
- После каждой копии проверяются размер и контрольная сумма. Раз в неделю
  последняя копия скачивается обратно и проверяется, что её можно прочитать
  (по желанию — что она целиком восстанавливается во временную базу).
- Если что-то не получилось — сообщение в тот же Telegram-чат, куда пишет
  watchdog (`TELEGRAM_CHAT_ID`). Если сервер умер целиком и сам написать не
  может — тревогу пришлёт внешний сервис healthchecks.io (копия не пришла
  вовремя).

До первого запуска бэкапа это выключено: нужны бакет и ключи, которые создаёт
владелец аккаунта Cloudflare (раздел «Как включить»).

## Где хранится и почему там

Выбран **отдельный приватный бакет Cloudflare R2**:

| Вариант | Цена | За | Против |
|---|---|---|---|
| **Отдельный бакет R2** | 0 ₽: 14 копий ≈ 3,5 ГБ входят в бесплатные 10 ГБ, скачивание бесплатно | другая компания, чем Hetzner: сгорит сервер или аккаунт Hetzner — копии целы; аккаунт Cloudflare уже есть; ключ можно ограничить одним бакетом | хранилище того же аккаунта Cloudflare, что и медиа |
| Hetzner Storage Box | от ≈ 3,2 €/мес | дёшево за большой объём | тот же провайдер и аккаунт, что и сервер; доступ по SSH/SFTP — нужен ещё один клиент в образе |
| Hetzner Object Storage | от ≈ 5 €/мес | S3, как R2 | тот же провайдер и аккаунт; платно с первого гигабайта |

Код работает с любым S3-совместимым хранилищем: переезд на Hetzner Object
Storage — смена четырёх переменных в `.env`.

Защита копий:

- бакет **приватный** (без публичного доступа и домена `r2.dev`), R2 шифрует
  данные на дисках сам;
- **отдельный ключ** с правом «Object Read & Write» только на этот бакет. Ключи
  медиа (`R2_*`) к копиям доступа не дают и наоборот. `manage.py check` не даст
  указать бакет или ключ медиа (`monitoring.E012`, `E013`): задача
  `cleanup_orphaned_media` чистит бакет медиа от всего, на что нет ссылок в БД,
  и стёрла бы копии;
- дополнительного шифрования ключом нет сознательно: потеря такого ключа
  означает потерю всех копий, а восстановление усложняется. Поэтому главное —
  двухфакторный вход в аккаунт Cloudflare и хранение ключа бэкапа только в
  `.env` сервера и в менеджере паролей.

## Как устроено

| Что | Когда | Где |
|---|---|---|
| `run_database_backup` | каждый день 01:15 МСК | очередь `celery`, контейнер `celeryworker` |
| `check_database_backup` | воскресенье 01:45 МСК | там же |

Celery Beat считает расписание по МСК: `CELERY_TIMEZONE` не задан, и Celery
берёт `TIME_ZONE = "Europe/Moscow"` из настроек Django. Время в имени копии —
UTC: копия в 01:15 МСК называется `mudaroba-ГГГГММДДT2215ссZ.dump` с датой
предыдущего дня.

Ежедневная копия:

1. `pg_dump --format=custom` (сжатый формат PostgreSQL) пишет в поток; поток
   режется на части по 16 МиБ и уходит в бакет multipart-загрузкой. **На диск
   сервера ничего не пишется**, в памяти одна часть.
2. Проверки: `pg_dump` завершился без ошибки, размер в бакете совпал с
   отправленным, рядом сохранён файл `….dump.sha256` (SHA-256 всего дампа).
3. Если дамп меньше 1 МиБ или меньше половины предыдущего — это почти
   наверняка пустая или урезанная база (как при вайпе июня 2026). Копия
   сохраняется, но ротация **не запускается**, чтобы не вытеснить хорошие копии,
   и приходит тревога.
4. Ротация: из всех копий остаются самые свежие за каждый из 7 последних дней,
   4 последних ISO-недель и 3 последних месяцев. Удаляются только объекты вида
   `postgres/mudaroba-ГГГГММДДTччммссZ.dump` и их `.sha256`.
5. Пинг healthchecks.io (если задан `DB_BACKUP_HEARTBEAT_URL`).

Еженедельная проверка:

1. Последняя копия не старше 26 часов (иначе ежедневный бэкап перестал
   работать).
2. Копия скачивается потоком (опять без диска): SHA-256 сверяется с файлом
   `.sha256`, `pg_restore --list` читает оглавление, в нём должны быть данные
   таблиц `catalog_product`, `orders_order`, `users`.
3. При `DB_BACKUP_TEST_RESTORE_ENABLED=true` — полное восстановление в
   одноразовую базу `mudaroba_restore_check` на том же PostgreSQL, подсчёт
   строк (товаров должно быть больше нуля) и удаление базы. Запускается, только
   если свободно не меньше «2 × размер базы + 4 ГиБ» (запас под образы
   следующего релиза), иначе — предупреждение в Telegram. По умолчанию
   выключено: на диске прода 2026-10-19 свободно ≈ 7 ГБ, включайте, когда
   станет заметно больше.

Бэкап и проверка не идут одновременно (блокировка в Redis-кэше). Сбой любой
стадии — сообщение «🔴 Бэкап базы Mudaroba: … — сбой» с причиной.

Ресурсы: `pg_dump`/`pg_restore` (пакет `postgresql-client` 15 в образе backend,
как и сервер) работают внутри `celeryworker` (лимит 640 МиБ, факт ≈ 380 МБ):
плюс несколько десятков МБ на `pg_dump` и 16 МиБ буфера. На сервере
PostgreSQL дамп — обычное чтение; восстановление строит индексы в пределах
`maintenance_work_mem` (64 МБ). Диск не используется, кроме пробного
восстановления.

Не входит в эту копию:

- **Qdrant** (векторы рекомендаций) — пересчитывается из базы:
  `manage.py sync_product_vectors --full` (DEPLOY.md §7).
- **Медиа** — лежат в R2 (бакет медиа), этим механизмом не копируются.
- **`.env`** с паролями и ключами — храните копию в менеджере паролей. Без него
  база восстановится, но придётся заново выпускать ключи всех сервисов.

Релизные бэкапы `scripts/release/create-backup.sh` (`~/backups/pharmaturk`,
перед деплоем, вместе с Qdrant) остаются как были.

## Как включить (делает владелец)

### 1. Бакет в Cloudflare R2

1. dash.cloudflare.com → **R2 Object Storage** → **Create bucket**.
2. Имя: `mudaroba-db-backups`. Location: Automatic (или подсказка «Eastern
   Europe» — ближе к серверу в Хельсинки). Storage class: Standard.
   **Create bucket**.
3. Ничего не включайте во вкладке Settings → Public access: ни custom domain,
   ни `r2.dev`. Бакет должен остаться приватным.

### 2. Ключ только для этого бакета

1. R2 Object Storage → **Manage API tokens** (справа) → **Create Account API
   token** (или User API token — тоже подойдёт).
2. Token name: `mudaroba-db-backup`.
3. Permissions: **Object Read & Write**.
4. Specify bucket(s): **Apply to specific buckets only** → `mudaroba-db-backups`.
5. TTL: Forever. **Create API Token**.
6. На следующей странице скопируйте **Access Key ID**, **Secret Access Key** и
   адрес **S3 endpoint** вида `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.
   Секрет показывается один раз — сразу сохраните все три значения в менеджер
   паролей: они понадобятся и для восстановления.

Ключи медиа (`R2_ACCESS_KEY_ID`) сюда не подходят — нужен именно новый ключ.

### 3. Внешний «пульс» (рекомендуется)

Нужен на случай, если сервер завис целиком (как 19.10) и сам не может написать.

1. Зарегистрируйтесь на healthchecks.io (бесплатный план — до 20 проверок).
2. **Add Check**: имя `mudaroba db backup`, Schedule → Simple: Period
   **1 day**, Grace **2 hours**.
3. Integrations → **Telegram** → следуйте подсказке (добавить бота в чат),
   отметьте эту проверку.
4. Скопируйте Ping URL вида `https://hc-ping.com/<uuid>`.

### 4. Ключи в `.env` прода

Под `deploy` на сервере, в `.env` проекта (рядом с `TELEGRAM_CHAT_ID`):

```dotenv
DB_BACKUP_ENABLED=true
DB_BACKUP_S3_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
DB_BACKUP_S3_REGION=auto
DB_BACKUP_S3_BUCKET=mudaroba-db-backups
DB_BACKUP_S3_ACCESS_KEY_ID=<Access Key ID из шага 2>
DB_BACKUP_S3_SECRET_ACCESS_KEY=<Secret Access Key из шага 2>
DB_BACKUP_HEARTBEAT_URL=https://hc-ping.com/<uuid>
DB_BACKUP_TEST_RESTORE_ENABLED=false
```

`TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID` уже должны быть заполнены — без них
`manage.py check` ругается `monitoring.E011`.

### 5. Деплой и первый запуск

1. Релиз с этим изменением (новый образ backend с `pg_dump`). Подходит и
   сокращённый backend-релиз (`backend_release.py`): миграций нет. После —
   смоук `/api` через сайт (рестарт nginx не нужен — [PROD_MEMORY.md](PROD_MEMORY.md),
   «nginx и новые адреса контейнеров»).
2. Проверка настроек и первая копия вручную (минута-две):

   ```bash
   docker exec mudaroba-celeryworker-1 poetry run python manage.py check
   docker exec mudaroba-celeryworker-1 poetry run python manage.py db_backup
   docker exec mudaroba-celeryworker-1 poetry run python manage.py db_backup --check
   ```

   Ожидается JSON со `"status": "ok"`; в бакете появятся
   `postgres/mudaroba-….dump` и `.sha256`, в healthchecks.io — первый пинг.
3. Дальше всё идёт по расписанию. Раз в месяц полезно открыть бакет и
   убедиться, что копии свежие.

Выключить: `DB_BACKUP_ENABLED=false` и пересоздать воркеры. Копии в бакете
останутся.

## Восстановление с нуля на новый сервер

Понадобятся: доступ к Cloudflare (или ключ бэкапа из менеджера паролей),
сохранённый `.env`, SHA последнего задеплоенного релиза (последний зелёный
коммит `main` или тег `vГГГГ.ММ.N`). Время — около часа.

### 1. Сервер

Создайте сервер в Hetzner (Ubuntu, не меньше 8 ГБ RAM и 40 ГБ диска),
установите Docker с Compose v2, создайте пользователя `deploy` в группе
`docker`. Сразу включите swap (раздел «Swap» в [PROD_MEMORY.md](PROD_MEMORY.md)).

```bash
git clone https://github.com/Mr-Fulani/PharmaTurk.git
cd PharmaTurk
git checkout <SHA_РЕЛИЗА>
# вставьте сохранённый .env
nano .env
chmod 600 .env
mkdir -m 700 ~/restore
```

### 2. Скачать последнюю копию

**Проще всего — через браузер:** Cloudflare → R2 → `mudaroba-db-backups` →
папка `postgres/` → самый свежий `mudaroba-….dump` → Download, и рядом его
`.sha256`. Затем со своего компьютера:

```bash
scp -i ~/3116 mudaroba-*.dump mudaroba-*.dump.sha256 deploy@<НОВЫЙ_IP>:restore/
```

**Или прямо на сервере**, ключом бэкапа (секрет не попадёт в историю команд):

```bash
read -rp 'Access Key ID: ' AWS_ACCESS_KEY_ID
read -rsp 'Secret Access Key: ' AWS_SECRET_ACCESS_KEY; echo
export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
ENDPOINT=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
aws_r2() {
  docker run --rm -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY \
    -e AWS_DEFAULT_REGION=auto -v ~/restore:/restore -w /restore \
    amazon/aws-cli:2.17.0 --endpoint-url "$ENDPOINT" "$@"
}
aws_r2 s3 ls s3://mudaroba-db-backups/postgres/
# выберите самую свежую копию и скачайте её вместе с .sha256
aws_r2 s3 cp s3://mudaroba-db-backups/postgres/mudaroba-<ДАТА>.dump .
aws_r2 s3 cp s3://mudaroba-db-backups/postgres/mudaroba-<ДАТА>.dump.sha256 .
```

Проверьте, что файл не повреждён (должно быть `OK`):

```bash
cd ~/restore && sha256sum -c mudaroba-*.dump.sha256 && cd -
```

### 3. Поднять пустой PostgreSQL и залить копию

```bash
docker compose -p mudaroba -f docker-compose.yml -f docker-compose.prod.yml up -d postgres
docker compose -p mudaroba -f docker-compose.yml -f docker-compose.prod.yml ps postgres
# дождитесь (healthy), затем:
docker exec -i mudaroba-postgres-1 sh -c \
  'pg_restore --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --no-owner --exit-on-error' \
  < ~/restore/mudaroba-<ДАТА>.dump
```

Восстановление идёт несколько минут и молчит, если всё хорошо. Проверка:

```bash
docker exec mudaroba-postgres-1 sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select count(*) from catalog_product" -c "select max(created_at) from orders_order"'
```

Число товаров должно быть порядка десятков тысяч, дата последнего заказа —
близка к дате копии. Если `pg_restore` упал с ошибкой — база неполная: удалите
том (`docker compose -p mudaroba … down -v` — только на **новом** сервере!) и
повторите с предыдущей копией.

### 4. Запустить сайт

```bash
./scripts/release/pull-images.sh --release-id <SHA_РЕЛИЗА>
# в .env: IMAGE_TAG=<SHA_РЕЛИЗА> и BACKEND_IMAGE_TAG=<SHA backend, если был отдельный>
docker compose -p mudaroba -f docker-compose.yml -f docker-compose.prod.yml up -d redis redis-cache qdrant
docker compose -p mudaroba -f docker-compose.yml -f docker-compose.prod.yml --profile ops run --rm migrate
docker compose -p mudaroba -f docker-compose.yml -f docker-compose.prod.yml up -d
curl -s http://localhost/api/health/
```

`migrate` на восстановленной базе того же релиза ничего не меняет — это
проверка, что схема и код совпадают.

### 5. Переключить трафик и доделать

1. Cloudflare → DNS: A-запись `mudaroba.com` (и `www`, если есть) — на новый IP.
   Остальные настройки Cloudflare/TLS — [DEPLOY.md](../DEPLOY.md) §4.
2. Рекомендации: `docker exec mudaroba-backend-1 poetry run python manage.py sync_product_vectors --full`.
3. Проверьте сайт: главная, категория, карточка, вход в админку, корзина.
4. Убедитесь, что бэкапы с нового сервера идут (`manage.py db_backup`, см.
   выше) и удалите `~/restore`.

Заказы и регистрации, сделанные между временем копии и аварией, потеряны —
сверьте их по Telegram-уведомлениям о заказах.

## Копия медиа: баннеры, карточки, страницы, услуги, фото товаров

С 22.10.2026, фото товаров — с 24.10.2026 (TD-013). Код: `backend/apps/monitoring/media_backup.py`, задачи `run_media_backup`
и `check_media_backup`, команда `restore_media_backup`.

### Простыми словами

Каждую ночь сервер копирует в тот же приватный бакет бэкапов (папка `media/`) картинки
и видео:

- `marketing/` — баннеры главной, карточки брендов и категорий (≈ 26 МБ, 112 файлов на
  22.10.2026);
- `pages/` — og-картинки страниц (≈ 2 МБ);
- `services/` — медиа услуг (≈ 184 МБ, 87 файлов);
- `products/` — фото товаров (≈ 20 ГБ, 97 720 файлов на 24.10.2026, половина — мебель).
  Без временных файлов парсеров `products/parsed/`. Хранение копии — около $0,30 в месяц.

Если файл пропадёт из бакета медиа (случайное удаление, очистка, как 14.06.2026), его копия
хранится ещё **30 дней**. О пропавших баннерах, страницах и услугах в Telegram приходит
сообщение: что пропало и до какого числа его можно вернуть. Фото товаров пропадают штатно
(перескрейп, `cleanup_orphaned_media`), поэтому о них сообщения нет. Пропажа больше половины
файлов разом — тревога для всех.

### Как устроено

| Что | Когда (МСК) | Где |
|---|---|---|
| `run_media_backup` | каждый день 02:00 — после бэкапа БД (01:15), до `cleanup-orphaned-media` (вс 03:30) | очередь `celery` |
| `check_media_backup` | воскресенье 02:30 | там же |

- Включается вместе с бэкапом БД: `MEDIA_BACKUP_ENABLED` по умолчанию равен
  `DB_BACKUP_ENABLED`, бакет и ключ — те же `DB_BACKUP_S3_*`. Новых ключей не нужно.
  Ключ бэкапов к бакету медиа доступа не имеет, поэтому файл идёт через воркер: читается
  из бакета медиа ключом `R2_*` и пишется ключом бэкапов, потоком частями по 8 МиБ
  (воркеру отведено 640 МиБ).
- Копия файла — `media/<ключ в бакете медиа>`, рядом манифест `media/.manifest.json`:
  ETag и размер источника, когда скопирован, с какого дня файла нет в источнике.
  Копируются только новые и изменённые файлы (другие ETag или размер).
- Ночь ограничена `MEDIA_BACKUP_TIME_BUDGET_SECONDS` (20 мин, лимит задачи — 25). Манифест
  сохраняется каждые 500 файлов и в конце. Прерванная копия продолжается следующей ночью
  со следующего файла. `last_success_at` пишется только у копии, дошедшей до конца,
  `last_run_at` — у каждой. Первую копию фото товаров (≈ 98 тыс. файлов, несколько часов)
  лучше запустить вручную, без предела времени:

  ```bash
  docker exec -d mudaroba-backend-1 sh -c '/app/.venv/bin/python manage.py shell -c "from apps.monitoring.media_backup import backup_media; print(backup_media())" > /tmp/media-seed.log 2>&1'
  ```
- Файл пропал из источника — копия остаётся `MEDIA_BACKUP_KEEP_DELETED_DAYS` (30) дней,
  потом удаляется; вернулся — счётчик сбрасывается. Пропала больше половины файлов
  разом — копия не трогается вовсе, тревога каждую ночь: это похоже на вайп, а не на
  правку баннеров. Если удаление намеренное — разовый запуск
  `media_backup.backup_media(allow_mass_missing=True)` из `manage.py shell`.
- Еженедельная проверка: последний запуск не старше 26 часов, последняя полная копия — не
  старше 8 дней, каждый файл манифеста лежит в копии того же размера.
- На dev копируется только свой префикс (`dev/marketing/…` → `media/dev/marketing/…`);
  другие окружения не читаются (`manage.py check` не даст указать пустой префикс —
  `monitoring.E015`). Префиксы — `MEDIA_BACKUP_PREFIXES`, исключения —
  `MEDIA_BACKUP_EXCLUDE_PREFIXES` (`products/parsed/`).
- Сбой копии или проверки — сообщение «🔴 Копия медиа Mudaroba: …» в тот же Telegram,
  что и бэкап БД.

Удаление неактуальных товаров ([STALE_PRODUCTS.md](STALE_PRODUCTS.md)) перед удалением
кладёт каждый файл товара сюда же (`media/<ключ>`), даже если ночная копия его ещё не
сделала; дальше эти копии живут по тем же правилам — 30 дней после пропажи из облака.

### Вернуть файлы

Команда сначала только показывает, что сделает. Путь — ключ в бакете медиа: файл или
префикс (на dev — с `dev/`):

```bash
# 1. Что есть в копии и чего нет в бакете медиа (ничего не меняет)
docker exec mudaroba-backend-1 /app/.venv/bin/python manage.py restore_media_backup marketing/banners/
# 2. Вернуть пропавшие файлы
docker exec mudaroba-backend-1 /app/.venv/bin/python manage.py restore_media_backup marketing/banners/ --apply
# 3. Заменить и испорченные (на месте, но другого размера) — только если уверены
docker exec mudaroba-backend-1 /app/.venv/bin/python manage.py restore_media_backup marketing/banners/ --apply --overwrite
```

Файл возвращается под тот же ключ, поэтому ссылки в баннерах и карточках снова работают.
Если вместе с файлом удалили и запись в админке (баннер, карточку), верните сначала
запись: файл без ссылки в БД `cleanup_orphaned_media` удалит снова в ближайшее
воскресенье.
