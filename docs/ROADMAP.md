# Roadmap Mudaroba

Обновлено: **21 августа 2026 года** после production-релиза и повторной сверки
кода, конфигурации, документации и эксплуатационного состояния. **22 октября
2026 года** отмечено сделанное в сентябре–октябре (раздел «Завершено в октябре
2026», P1.5, P1.6); **24 октября** — медикаменты (P1.9 и «Завершено в октябре»);
остальные разделы — по сверке 21 августа.

Этот документ разделяет:

1. актуальные открытые задачи — то, что ещё требует работы или проверки;
2. завершённые изменения текущего аудита;
3. исторический snapshot июня 2026 года — полезный контекст, но не автоматически актуальный backlog.

Приоритеты: **P0** — блокирует безопасный production-релиз; **P1** — ближайший спринт; **P2** — системный техдолг; **P3** — улучшение продукта.

## Текущий baseline

- продукт и API называются Mudaroba; `PharmaTurk` остаётся историческим именем репозитория;
- Python 3.12.13, Django 5.2.17;
- Node.js 22.23.2, Next.js 15.5.28;
- PostgreSQL 15.18, Redis 7.4.10, Qdrant 1.18.3;
- OpenSearch исключён из кода и актуального Compose как неиспользуемый; legacy
  container остановлен, а его image/volume временно сохранены только для rollback;
- каталог содержит 19 корневых доменов;
- криптооплата реализована через CoinRemitter, но production credentials пока
  принадлежат тестовому TCN-кошельку; реальные платежи до замены wallet
  credentials не готовы;
- VAPI и AI API доступны только staff;
- seed каталога должен выполняться только явно;
- production settings используют fail-fast вместо опасных fallback.

## P0 — статус release gates

Все application release gates для ревизии `0bcfc8a` выполнены 21 августа 2026
года. Эта ревизия находилась одновременно в `main`, production containers и
immutable GHCR images; публичные smoke-проверки прошли. Открытых P0-дефектов в
коде не зафиксировано. Реальный CoinRemitter staging E2E остаётся внешней P1
проверкой и не должен подменяться ручным изменением статусов в БД.

### P0.1 Полная интеграционная проверка на PostgreSQL

Чистая PostgreSQL 15.18 и полный suite подтверждены 21 августа 2026 года:
**963 passed**, 4 deprecation warnings, migration drift отсутствует. Dedup и
создание partial unique indexes корзины разделены на миграции `0008`/`0009`.
Production dump был восстановлен только во временную копию volume, после чего
миграции и проверки были успешно выполнены без записи в исходный production
volume. PostgreSQL и Qdrant backups скопированы за пределы Docker volumes, их
контрольные суммы совпали на сервере и в локальной копии.

Критерии готовности:

- миграции применяются с нуля и поверх production-like snapshot;
- повторный и конкурентный webhook не списывает остаток дважды;
- нет известных payment/order failures в карантине CI;
- `makemigrations --check --dry-run` не создаёт новых файлов.

### P0.2 Container, CI и production smoke-test

Локальный gate повторно выполнен 21 августа 2026 года отдельными одноразовыми
`mudaroba-predeploy-*` и `mudaroba-smoke-*` projects: Compose merge,
PostgreSQL/Redis/Qdrant, SHA-tagged production images, non-root runtime,
одноразовые migrations, Gunicorn readiness/liveness, Nginx security headers и
canonical redirect подтверждены. Временные containers и volumes удалены.
Backend использует воспроизводимый `torch=2.13.0+cpu`; frontend dependency audit
— 0 vulnerabilities.

Container gate затем прошёл на GitHub-hosted CI runner: frontend/backend tests,
dependency audits, Compose validation, production image build и публикация
immutable SHA-тегов завершились успешно. После production deploy главная
страница, `/api/live/` и `/api/health/` отвечали `200`; restart count оставался
нулевым, критических ошибок в проверенном окне логов не обнаружено.

### P0.3 Production secrets и TLS

Production использует явные hosts/origins, уникальные application/database
credentials и раздельные Redis logical DB для broker/cache/result. Публичная
повторная проверка подтвердила redirect с HTTP на canonical HTTPS, HSTS и
согласованные security headers. `/api/live/` проверяет процесс, а readiness
`/api/health/` — PostgreSQL и Redis cache; оба endpoint отвечали `200` после
deploy.

CI теперь выполняет blocking Gitleaks scan по полной доступной Git history.
Локальный Gitleaks 8.28.0 просканировал 761 commits и нашёл 5 curl-auth
совпадений в одном достижимом commit со старыми AI-инструкциями. Проверка
21 августа подтвердила, что все пять значений — невалидные localhost-only JWT
placeholders, а не внешние credentials. Для них добавлены только точные
fingerprints в `.gitleaksignore`; повторный history scan чистый. Rewrite history
и ротация Telegram/email/Resend/VK/Serper по этим срабатываниям не требуются.

Локальный `.env` игнорируется Git и его права в ходе аудита ужесточены с `0644`
до `0600`. Текущие чувствительные значения не найдены в Git history, локальных
логах или неигнорируемых артефактах. По принятому операторскому решению старые
Telegram/email/Resend/VK/Serper credentials не ротировались: обязательная
ротация нужна при признаках экспозиции, отзыве доступа либо по регламентному
сроку. Production Redis URLs явно разделены на `/0`, `/1` и `/2`; fail-fast не
позволит запустить production с общим target.

### P0.4 Очистка legacy PDF-чеков

Новый код пишет и читает чеки только из HMAC-namespaced ключей. Безопасный
inventory выявил 10 legacy PDF: 6 в корневом и 4 в dev namespace. Все 10 сначала
скопированы в recoverable quarantine, затем удалены только старые предсказуемые
ключи; итоговая повторная инвентаризация показала `legacy=0`. HMAC-namespaced
объекты не затрагивались. Команда `cleanup_legacy_receipts` по-прежнему требует
`--apply`, точного `--confirm-bucket` и непредсказуемого
`--quarantine-prefix`, а при ошибке копирования не удаляет источник.

## P1 — ближайший спринт

### P1.0 Production-кошелёк CoinRemitter и E2E оплаты

Диагностика 21 августа 2026 года подтвердила, что production API key относится
к тестовому кошельку TCN. При заказе на `18884.00 RUB` CoinRemitter вернул
HTTP 400 / error `1001`: инвойс превышает лимит `10 TCN`. Значение
`COINREMITTER_COIN=USDT` не выбирает кошелёк: фактическую монету определяет
пара `COINREMITTER_API_KEY` / `COINREMITTER_API_PASSWORD`. Поэтому изменение
только `COINREMITTER_COIN` проблему не исправит.

До закрытия задачи TCN разрешён только в изолированном local/staging-контуре и
только для небольшого инвойса в пределах лимита провайдера. Нельзя подменять
сумму production-заказа тестовой суммой: authoritative webhook verification
должна обнаружить расхождение. Реальную криптооплату на витрине следует считать
неготовой и не предлагать покупателям до прохождения критериев ниже.

План включения USDT TRC20:

1. создать или выбрать реальный кошелёк `USDT TRC20` в CoinRemitter;
2. выпустить относящиеся именно к нему API Key и API Password;
3. безопасно заменить в production `.env` значения
   `COINREMITTER_API_KEY`, `COINREMITTER_API_PASSWORD` и установить
   `COINREMITTER_COIN=USDTTRC20`, не передавая секреты через Git, логи или чат;
4. перезапустить backend и все Celery-процессы без пересоздания state volumes;
5. создать минимальный тестовый инвойс без отправки реальных средств и
   подтвердить, что provider возвращает USDT TRC20, корректные fiat/crypto
   суммы, invoice URL и expiry;
6. провести контролируемый минимальный платёж на staging/production только
   после успешного шага 5;
7. подтвердить совпадение provider id, order binding, валюты и суммы;
8. принять pending/paid/expired webhook, повторить webhook и убедиться в
   идемпотентности;
9. смоделировать provider timeout и неверный payload;
10. проверить остатки, статус заказа, уведомление, чек и read-only
    `reconcile_coinremitter` без drift.

Критерий закрытия: реальные wallet credentials установлены, TCN-ошибка больше
не воспроизводится, тестовый инвойс и webhook проходят, reconciliation не
находит расхождений, а rollback предыдущего `.env` сохранён в защищённом
операционном backup.

Read-only команда `reconcile_coinremitter` и эксплуатационный runbook уже
добавлены. Исправление drift должно идти через подлинный webhook или утверждённую
операционную процедуру, а не через прямую запись статуса в БД.

### P1.1 OpenAPI как проверяемый контракт

Схема теперь генерируется без ошибок и защищена regression test; CI не допускает
рост выше текущего baseline **573 warnings (570 unique)**. Конкретные проблемы
path parameters, неявного поля `product_type` и конфликтующих enum names закрыты;
оставшийся baseline состоит только из отсутствующих return type hints у старых
`SerializerMethodField` в пяти serializer-модулях. Свести его к нулю или к
короткому документированному allowlist. При каждом исправлении снижать
`OPENAPI_UNIQUE_WARNING_BASELINE`, генерировать схему в CI и сравнивать
изменения и не хранить заведомо устаревший `schema.yml`.

Особое внимание: permissions, ограничения VAPI/AI serializers, throttled auth/upload responses, health `503` и webhook errors.

### P1.2 SEO-аудит после обновления Next.js

Повторно проверить на Next.js 15.5.28:

- только `404` API превращается в `notFound`, а timeout/5xx остаются временной ошибкой;
- canonical/hreflang для ru без префикса и en с `/en`;
- отсутствие дублей `og:url`/hreflang из `_document`;
- единый sitemap, trailing slash и `/ru/*` redirect;
- noindex для cart/checkout/profile/auth/search/pagination.

Проверка должна включать rendered HTML, а не только чтение JSX.

### P1.3 Производительность product resolve и SSR

Убрать последовательный перебор всех доменных ViewSet при resolve slug. Целевая схема — единый реестр `slug -> domain type -> id`, затем один прямой dispatch. Добавить query-count и latency tests.

Для публичных SSR-страниц определить cache policy (`s-maxage`/`stale-while-revalidate`) и проверить Cloudflare Cache Rules. Персональную валюту и корзину не кэшировать в общем HTML.

### P1.4 Медиа вне request workers

Основной путь изображений/видео должен идти через R2/CDN. Django proxy оставить контролируемым fallback с cache-first, range support, размерными лимитами и отдельными метриками. Не допускать длительного video streaming через API workers.

### P1.5 Наблюдаемость

В репозитории подтверждены Prometheus endpoint, JSON logging и опциональный Sentry. Grafana, ELK и готовые dashboards в состав проекта не входят.

Базовая доставка production-инцидентов закрыта 2026-09-04: watchdog в
обслуживаемой Celery queue проверяет homepage/liveness/readiness, отправляет
дедуплицированные Telegram alert/recovery и имеет operations runbook. Полный отказ
самого хоста требует отдельного off-host synthetic monitor: после зависания
2026-10-19 он описан в [PRODUCTION_MONITORING_RUNBOOK.md](PRODUCTION_MONITORING_RUNBOOK.md)
(HetrixTools, проверки `/api/health/` и главной раз в минуту, Telegram). Подключает
владелец в веб-интерфейсе провайдера; внутренний watchdog включается
`PRODUCTION_WATCHDOG_ENABLED=true` в прод `.env`.

Нужно добавить:

- dashboard/alerts для 5xx, p95/p99, DB pool, очередей Celery и payment failures;
- correlation/request id в web и tasks;
- alert на backlog/retry/dead-letter-like состояния;
- synthetic checks для homepage, catalog, checkout readiness и webhook reachability;
- runbook с владельцем каждого алерта.

### P1.6 Тестовые и lint-gates

Добавлены schema, receipt-isolation, trusted-IP throttle и критические permission
tests. Flake8 с 2026-09-05 — блокирующий инкрементальный gate
(`scripts/flake8_quality_gate.py`): общий baseline ограничен (`--max-total`),
изменённые файлы не могут добавлять нарушения, новые файлы — без нарушений.
Остаётся:

- завершить permission matrix для всех API routes;
- frontend tests visual search ошибок `413/415/429`;
- заменить 44 оставшихся `<img>` (hooks warnings уже закрыты), снижая обязательный
  `--max-warnings 44`, и обновить deprecated ESLint 8; online audit полного и
  production-only дерева уже чист;
- постепенно снижать общий flake8 baseline (`--max-total` в CI).

### P1.7 Надёжность checkout/payment orchestration

Кодовая часть закрыта 4 сентября 2026 года. Crypto checkout атомарно создаёт
pending order и durable `CryptoInvoiceRequest`, а `invoice/create` выполняется
Celery после DB commit. Повторные HTTP/Celery-запросы не создают второй локальный
платёж; пропущенный broker publish подбирает периодический dispatcher. Поскольку
официальный CoinRemitter API не предоставляет provider idempotency key,
неоднозначный результат безопасно карантинируется как `uncertain` без
автоматического повтора. Повторная публикация pending intent ограничена
cooldown, чтобы при остановке worker не раздувать очередь. Scheduled
reconciliation отмечает stale claims и пишет структурированный drift/outbox
summary с warning для `uncertain`/`failed`.

Реальный USDT TRC20 E2E остаётся отдельным внешним критерием P1.0: production
credentials 4 сентября по read-only `wallet/balance` всё ещё указывают на
`TCN / TestNet`, несмотря на строковое `COINREMITTER_COIN=USDT`.

### P1.8 Browser security policy

Security headers включены, но строгий CSP пока не развёрнут из-за inline-кода
Next.js/analytics. Ввести nonce/hash-based CSP сначала в report-only, собрать
нарушения, затем включить enforcement без `unsafe-inline` для пользовательского
контента.

Статус 24.10.2026 (TD-018): CSP выкатывается в режиме Report-Only с приёмником
отчётов `/api/csp-report/`, refresh JWT — HttpOnly cookie от backend
([SECURITY_CSP.md](SECURITY_CSP.md)). Следующие шаги — enforce через неделю
отчётов, затем nonce вместо `unsafe-inline` (TD-033).

### P1.9 Медикаменты: каталог, переводы и SEO

Сделано 23–24.10.2026 — в «Завершено в октябре». Открыто:

- **Массовая обработка остального каталога** — отложена владельцем 24.10.2026, в техдолге (TD-032).
- **Пересчёт названия и SEO опубликованных лекарств кодом без модели** (TD-028). После ближайшего
  релиза — переобработать 10 лекарств пилота 5 (`~/ai-pilot/med50p5.rest10.ids`) под PR #170.
- **Контроль запрещённых к ввозу препаратов** (TD-024).
- **SEO-план, пункты 3–6** — код готов 24.10.2026, ждёт релиза (PR #174): страницы препаратов
  `/drugs/<slug>`, 4 статьи блога, FAQPage, LEVOTIRON в «Гормонах» ([MEDICINE_DRUG_PAGES_AND_BLOG.md](MEDICINE_DRUG_PAGES_AND_BLOG.md)).
  A-FERIN, KATARIN, AERIUS — страницы выключены (решение владельца 24.10). Открыто: товары со спросом,
  которых нет (Solcoseryl, смекта и др.), — с согласия владельца; поиск по действующему веществу.
- **Проверка нижних ≈ 167 тыс. записей памяти абзацев** — сделано 26.10.2026 через Claude API (TD-025 закрыт).

Пометку «неофициальный перевод» и кнопку «оригинал на турецком» владелец решил не делать (24.10.2026).

## P2 — архитектура и техдолг

### P2.1 Унификация каталога

19 доменных моделей и связанные generic-строки создают сложность в resolve, sitemap, favorites и serializers. Планировать постепенный slug registry и единый контракт domain adapters, без большого одномоментного переписывания.

### P2.2 Нормализация slug

Устранить дублирующий `deduplicateSlug` data-миграцией и валидацией на всех входах: admin, parser, VAPI и AI. Старые URL сохранить через таблицу redirects.

### P2.3 Декомпозиция крупных файлов

Разбивать `catalog/views.py`, большие serializers и frontend product/category pages при каждом функциональном изменении. Цель — изолированные domain modules и тестируемые selectors/services, а не механический split без границ ответственности.

### P2.4 Персональные рекомендации

Не показывать trending как «персональную» выдачу. Сначала реализовать пользовательские сигналы, обновление embedding, privacy/retention policy, дедупликацию вариантов, feature flag и offline/online quality metrics. Критерии: [PERSONALIZED_RECOMMENDATIONS.md](PERSONALIZED_RECOMMENDATIONS.md).

### P2.5 Документация и релизы

- сократить множество пересекающихся Markdown-файлов в корне;
- каждый legacy-документ либо актуализировать, либо явно пометить датой/статусом;
- вести CHANGELOG и теги `vYYYY.MM.N`;
- для каждого production deploy хранить проверяемый checklist и rollback target.

### P2.6 Потоковые выгрузки и privileged ingestion

- ~~YML feed сейчас строит XML целиком и создаёт риск памяти/N+1; генерировать его
  фоново, хранить готовый объект и отдавать с ETag~~ — сделано 2026-10-27:
  `catalog.generate_yml_feeds` каждые 6 ч, готовые файлы с ETag, подкатегории
  потоком ([VK_YML_FEED.md](VK_YML_FEED.md));
- унифицировать оставшиеся privileged download paths (`catalog/signals.py`,
  `parser_media_handler.py`, `vk_market_sync.py`) с bounded/pinned safe fetcher;
- ~~вынести broker/cache/result из логических Redis DB в раздельные
  instances~~ — сделано 2026-10-19 (PR #100): кэш Django — отдельный контейнер
  `redis-cache` (`allkeys-lru`, 128mb), брокер и результаты Celery — `redis`
  (`noeviction`, 128mb); managed instances — только если вырастет нагрузка.

## P3 — продуктовые улучшения

- Google Merchant feed поверх уже существующего YML-контракта;
- Core Web Vitals/CrUX и Search Console monitoring;
- автоматизированная проверка ru/en structured data;
- quality dashboard рекомендаций и визуального поиска;
- SLO для checkout, платежей и freshness каталога.

## Завершено в октябре 2026

- **Бэкап БД вне сервера** — ежедневный `pg_dump` во внешний приватный бакет R2
  отдельным ключом, ротация 7/4/3, еженедельная проверка, Telegram (PR #102,
  [DB_BACKUP.md](DB_BACKUP.md)).
- **Память и Redis** — кэш Django в отдельном `redis-cache` (`allkeys-lru`), брокер
  и результаты Celery в `redis` (`noeviction`), `mem_limit` у каждого сервиса,
  сумма ≤ 7 ГиБ (PR #100, #101, #104, #108, [PROD_MEMORY.md](PROD_MEMORY.md));
  байты картинок больше не пишутся в Redis (#89); проверка места перед pull и
  очистка старых образов после деплоя (#88, [PROD_DISK_AND_REDIS.md](PROD_DISK_AND_REDIS.md)).
- **Origin и обслуживание базы** — Cloudflare Full (strict) на 443, ночная чистка
  сессий и логов парсеров (PR #103, в main вместе с #102;
  [PROD_ORIGIN_SECURITY.md](PROD_ORIGIN_SECURITY.md), [PROD_DB_MAINTENANCE.md](PROD_DB_MAINTENANCE.md));
  ответы 500 не кэшируются Cloudflare (#115); Beat по crontab (МСК) вместо
  интервалов (#106).
- **AI-прогоны** — раздел «AI-прогоны» в админке (#93), перевод абзацев инструкций
  через Batch API кнопками (#123), тексты не медицинских товаров правилами (#96),
  лекарства кодом и памятью переводов (#95), отсечение сдвинутых переводов (#121,
  #122) — [AI_RUNS_ADMIN_GUIDE.md](AI_RUNS_ADMIN_GUIDE.md), [AI_GUIDE.md](../AI_GUIDE.md).
  Массовые прогоны запускает владелец (пилот → исправления → следующая партия).
- **Напоминания о Списке заявки** — email и Telegram, выключены по умолчанию,
  включаются в админке (#142, [CART_REMINDERS.md](CART_REMINDERS.md)).
- **Режимы парсеров** — товар по ссылке, категория до конца, весь сайт / профиль
  Instagram у всех каталожных парсеров (#134 в релизе #135,
  [PARSER_MODES.md](PARSER_MODES.md)); Bershka/Pull&Bear/Massimo Dutti через API
  `/itxrest` (#94); ilacabak удалён (#131); аудит парсеров —
  [AUDIT_2026-10-20_PARSERS.md](AUDIT_2026-10-20_PARSERS.md).
- **Каталог и SEO** — история slug и 301 со старого URL (#86), аналитика воронки
  GA4 + Метрика (#111, [ANALYTICS_EVENTS.md](ANALYTICS_EVENTS.md)), страница бренда
  без детоаста jsonb и N+1 (#113, #117, #118,
  [BRAND_PAGE_PERFORMANCE.md](BRAND_PAGE_PERFORMANCE.md)).
- **Скорость на телефоне (27.10)** — CLS от шрифта и поиска, фото карточки 800 px,
  фильтр брендов, аналоги лекарств и фильтры-атрибуты без лишней работы БД
  (#243, #245, #247–#251, [PERFORMANCE_CWV_2026-10.md](PERFORMANCE_CWV_2026-10.md)).
- **Наблюдаемость** — внешний off-host монитор описан (см. P1.5).
- **Переводы инструкций лекарств (23–24.10)**:
  - Haiku со скептиком проверил верхние ≈ 50 % памяти абзацев и исправил 23 939 записей; на сайт
    исправления внесены точечной заменой строк по турецкому исходнику (1 602 строки в 133 лекарствах);
  - 546 новых абзацев остального каталога переведены Haiku, без OpenAI;
  - словарь МНН пересобран по АТХ и Wikidata (662 исправления: «Кетиапин» → «Кветиапин»,
    «Клоразин» → «Клозапин»);
  - словарь брендов кириллицей — 6 432 бренда, по латинскому чтению упаковки, как ищут покупатели.

  Подробно — [MEDICINE_TRANSLATION_KNOWLEDGE_BASE.md](MEDICINE_TRANSLATION_KNOWLEDGE_BASE.md).
- **SEO карточек лекарств кодом** (#167, #168, #170, [SEO_MEDICINES.md](SEO_MEDICINES.md)):
  - бренд кириллицей и латиницей, вещество, форма, «из Турции»;
  - рецепт и холодовая цепь в описании, без «без рецепта»;
  - препараты строгого учёта не продвигаются;
  - модель пишет только короткое описание.
- **Названия лекарств кодом** (#164, #169): вещество в скобках («MAJEZIK (флурбипрофен) …»),
  растворы для диализа и в/в растворы, пастилки, пластыри, порошки с растворителем. Шаблон строится
  у 10 142 из 12 917 названий. Производитель передаётся модели отдельно от бренда.
- **SEO категорий медикаментов** (#165): страницы подкатегорий и подборок, мета корня «Лекарства из
  Турции» ([MEDICINE_LANDING_PAGES.md](MEDICINE_LANDING_PAGES.md)).

## Завершено в аудите августа 2026

### Платежи

- webhook больше не доверяет входному статусу: invoice повторно читается через авторизованный CoinRemitter API;
- проверяются identity, order binding, сумма, валюта и paid amount;
- транзакция и row locks защищают от двойного списания остатков;
- повтор webhook идемпотентен, provider outage возвращает retryable error;
- исправлена передача `Decimal` и хранение суммы/валюты заказа.

### Доступ и входные данные

- глобальный DRF default изменён на `IsAuthenticated`;
- публичные endpoints открыты явно;
- VAPI/AI требуют staff, testimonial create — авторизацию;
- добавлена строгая сериализация query/body параметров VAPI и AI;
- login/token endpoints и загрузки имеют отдельные throttles.

### Загрузка изображений

- общий safe fetcher закрывает private/mixed DNS, DNS rebinding, userinfo и нестандартные порты;
- redirect/download/pixel limits ограничены;
- проверяются реальный формат и соответствие MIME;
- temp uploads и visual search имеют server/client limits и безопасные ошибки;
- тяжёлые ML-модели загружаются лениво.

### Production defaults и инфраструктура

- production запускается fail-fast при placeholder secret или wildcard hosts;
- TLS/HSTS стали управляемыми env, cookies secure вне debug;
- readiness отделён от liveness;
- DB/Redis connection timeouts ограничены, а stateful dev-порты привязаны к
  `127.0.0.1`;
- зависимости frontend/backend устанавливаются воспроизводимо из lock-файлов;
- версии runtime/images выровнены и Qdrant зафиксирован;
- OpenSearch удалён как неиспользуемый;
- зависимости больше не ставятся при production boot, Redis cache не очищается при каждом старте;
- включены persistent PostgreSQL connections;
- CI проверяет frontend, backend, зависимости, миграции и Compose config.
- GitHub Actions переведены на Node 24-compatible checkout/setup, Docker login
  и Gitleaks v3;
- backend image build получает безопасное build-only окружение и не конфликтует
  с production fail-fast;
- новые PDF-чеки используют HMAC namespace, legacy predictable fallback удалён.

## Исторический snapshot: июнь 2026

Ниже — статус пунктов прежнего аудита. Номера сохранены для ссылок из старых обсуждений. Статус «перепроверить» означает, что наблюдение нельзя считать закрытым только по старому номеру строки после обновления зависимостей и большого изменения кода.

| Старый пункт | Наблюдение июня 2026 | Статус на 2026-08-09 |
| --- | --- | --- |
| P0.1 | `/ru/*` дубли и неверные redirect | исправлено в июне; нужен regression smoke после Next 15 |
| P0.2 | backend timeout/5xx превращался в SEO 404 | перепроверить в P1.2 |
| P0.3 | canonical ряда EN-страниц указывал на RU | перепроверить в P1.2 |
| P0.4 | старый `SEO.tsx` имел инвертированную locale-логику | перепроверить/унифицировать в P1.2 |
| P1.1 | до ~20 последовательных dispatch при product resolve | открыт, P1.3 |
| P1.2 | публичный SSR HTML без согласованного edge cache | открыт, P1.3 |
| P1.3 | медиа занимало sync workers | частично смягчено gthread; целевой CDN-путь открыт, P1.4 |
| P1.4 | конфликтующие meta из `_document` | перепроверить, P1.2 |
| P1.5 | два sitemap | backend route удалён; проверить rendered sitemap в P1.2 |
| P1.6 | небезопасные settings defaults | закрыто текущим аудитом |
| P1.7 | CI отсутствовал | закрыто текущим аудитом |
| P2.1 | install/cache flush на каждом boot | основные причины устранены; boot smoke входит в P0.2 |
| P2.2 | новое DB connection на каждый request | закрыто (`CONN_MAX_AGE` + health checks) |
| P2.3 | slug-дубли лечились в нескольких местах | открыт, P2.2 |
| P2.4 | серийная пагинация брендов в SSR | закрыто в июле 2026 |
| P2.5 | лишние media proxy hops/cache | частично открыто, P1.4 |
| P2.6 | гигантские компоненты/views | открыт, P2.3 |
| P2.7 | мелкие canonical/sitemap расхождения | перепроверить, P1.2 |
| P2.8 | неполный Product JSON-LD | включить в P1.2 |
| P2.9 | персонализация фактически возвращала trending | открыт, P2.4 |

Исторические номера не определяют новый приоритет: для планирования используются актуальные разделы выше.
