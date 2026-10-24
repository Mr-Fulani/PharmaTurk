# Документация Mudaroba

Индекс документации репозитория. Актуальное имя продукта — **Mudaroba**; `PharmaTurk` встречается в исторических именах путей, репозитория и мобильного клиента.

## Что считать источником правды

При расхождении документов используйте следующий порядок:

1. исполняемый код, миграции, `pyproject.toml` / `poetry.lock` и `package.json` / `package-lock.json`;
2. `.env.example`, production env example и Compose/Dockerfile текущей ветки;
3. [корневой README](../README.md), [README для разработчика](../README-DEV.md) и [актуальный roadmap](ROADMAP.md);
4. тематические руководства;
5. старые analysis/summary/plan документы — только как исторический контекст.

Документ без даты проверки не следует использовать как production runbook без сверки с кодом.

## Основные документы

| Документ | Назначение | Статус |
| --- | --- | --- |
| [AUDIT_2026-08-09.md](AUDIT_2026-08-09.md) | полный security/architecture/documentation audit, проверки и release gates | итоговый отчёт 2026-08-09 |
| [README.md](../README.md) | продукт, архитектура, быстрый старт и security baseline | актуализирован 2026-08-21 |
| [README-DEV.md](../README-DEV.md) | локальная разработка, тесты, seed и permissions | актуализирован 2026-08-21 |
| [ROADMAP.md](ROADMAP.md) | текущий backlog и отделённый snapshot июня 2026 | актуализирован 2026-08-21, сделанное в октябре — 2026-10-22 |
| [TECH_DEBT.md](TECH_DEBT.md) | реестр подтверждённого открытого технического долга | актуализирован 2026-10-22 (раздел за октябрь 2026) |
| [SOURCE_OFFER_CART_VERIFICATION_PLAN.md](SOURCE_OFFER_CART_VERIFICATION_PLAN.md) | рабочий план проверки цены и наличия первоисточника в корзине и checkout | активен с 2026-08-27 |
| [PRODUCT_CARD_SOURCE_REFRESH_PLAN.md](PRODUCT_CARD_SOURCE_REFRESH_PLAN.md) | план и статус обновления цены/вариантов спарсенной карточки при открытии | активен с 2026-08-29 |
| [SOURCE_OFFER_OPERATIONS_RUNBOOK.md](SOURCE_OFFER_OPERATIONS_RUNBOOK.md) | rollout, метрики, alerting и безопасный повтор source-offer checks; поиск продавца БАДов (`discover_supplement_stock_offers`) | актуализирован 2026-08-31, переменные обновления карточки и поиск продавца БАДов — 2026-10-22 |
| [PRODUCTION_MONITORING_RUNBOOK.md](PRODUCTION_MONITORING_RUNBOOK.md) | synthetic/readiness watchdog, Telegram delivery, дедупликация, внешняя проверка доступности и triage | актуализирован 2026-10-19 |
| [PROD_DISK_AND_REDIS.md](PROD_DISK_AND_REDIS.md) | что занимает диск прода, очистка образов при деплое, лимиты Redis и ротация логов | снимок 2026-10-18 |
| [DB_BACKUP.md](DB_BACKUP.md) | ежедневный бэкап базы в отдельный бакет R2, проверка, включение и восстановление с нуля на новом сервере | 2026-10-19 |
| [PROD_MEMORY.md](PROD_MEMORY.md) | лимиты памяти контейнеров, брокер и кэш в разных Redis, swap, применение без потери очередей | после инцидента 2026-10-19 |
| [PROD_DB_MAINTENANCE.md](PROD_DB_MAINTENANCE.md) | ночная чистка сессий Django и логов парсеров, первая чистка, VACUUM / VACUUM FULL и их блокировки; autovacuum таблиц товаров после массовых правок | снимок 2026-10-19, autovacuum — 2026-10-21 |
| [PROD_ORIGIN_SECURITY.md](PROD_ORIGIN_SECURITY.md) | Cloudflare Full (strict) с Origin Certificate на 443, закрытие прямого доступа (Hetzner Cloud Firewall), IPv6-обход | 2026-10-19 |
| [SECURITY_CSP.md](SECURITY_CSP.md) | CSP в режиме Report-Only, приёмник `/api/csp-report/`, refresh JWT в HttpOnly cookie, шаги перехода в enforce (TD-018/TD-033) | 2026-10-24 |
| [PROD_ROOT_MAINTENANCE.md](PROD_ROOT_MAINTENANCE.md) | под root: обновления ОС и Docker, swap, журнал systemd, перезагрузка в тихий час | 2026-10-19 |
| [AUDIT_2026-10-19_PARSERS_CATALOG.md](AUDIT_2026-10-19_PARSERS_CATALOG.md) | почему не запускаются Instagram/UmmaLand/Akakce, товары без картинки и цены, сброс интервалов beat при деплое | отчёт 2026-10-19 |
| [AUDIT_2026-10-20_PARSERS.md](AUDIT_2026-10-20_PARSERS.md) | живые пробы всех парсеров (на 20.10 их было 13; сейчас 11 — ilacabak удалён в #131), найденные и исправленные баги, что решить по Instagram/UmmaLand/akakce | отчёт 2026-10-20 |
| [PARSER_MODES.md](PARSER_MODES.md) | три режима каждого парсера (товар, категория до конца, весь сайт / профиль Instagram), как запустить в админке, откуда берутся категории | 2026-10-21 |
| [PAID_WEB_ACCESS_SERVICES.md](PAID_WEB_ACCESS_SERVICES.md) | Bright Data proxy/Web Unlocker: тарифы, бюджет, возможности и безопасное переиспользование | актуализирован 2026-08-31 |
| [SOURCE_OFFER_CART_API.md](SOURCE_OFFER_CART_API.md) | Cart API: verification fields, issue codes, 409/503 и действия клиента | актуализирован 2026-08-27 |
| [DEPLOY.md](../DEPLOY.md) | production deployment и rollback | проверен 2026-08-21, актуализирован 2026-10-22 (бэкап в R2, origin 443, Redis) |
| [scripts/release/README.md](../scripts/release/README.md) | скрипты релиза: проверка, миграции, выкладка, откат, сокращённый backend-релиз | актуализирован 2026-10-18 |
| [MANAGEMENT_COMMANDS.md](MANAGEMENT_COMMANDS.md) | справочник management-команд, которые не описаны в тематических доках; устаревшие помечены | 2026-10-22 |
| [DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md) | правила SEO, backend/frontend и e-commerce | актуализирован 2026-10-23 |
| AUDIT_2026-10-15_SEO_GROWTH.md | аудит качества, SEO и воронки 15.10: P0 (фейковая карта в checkout, аналитика, заявка на лекарства, Rx-разметка, картинки под Disallow, сырой контент, пустые категории) закрыты к 17.10 | локальный отчёт владельца, в репозиторий не коммитится (`.gitignore`) |

## Доменная документация

### Каталог, SEO и frontend

- [CATALOG_FAVORITES_PROXY_MEDIA.md](CATALOG_FAVORITES_PROXY_MEDIA.md) — доменные id, избранное, R2 и proxy-media;
- [FURNITURE_ATTRIBUTES_BACKFILL.md](FURNITURE_ATTRIBUTES_BACKFILL.md) — безопасный backfill характеристик мебели;
- [AUTO_PARTS_AI_DESIGN.md](AUTO_PARTS_AI_DESIGN.md) — дизайн домена автозапчастей: OEM-номера, применимость, обработка без LLM;
- [HOW_TO_ORDER_PAGE.md](HOW_TO_ORDER_PAGE.md) — страница «Как заказать»: разделы, SEO, позиция баннеров `how_to_order`;
- [MEDICINE_LANDING_PAGES.md](MEDICINE_LANDING_PAGES.md) — посадочные страницы медикаментов: SEO подкатегорий и корня, 17 подборок по правилам АТХ/формы, адреса, админка;
- [MEDICINE_DRUG_PAGES_AND_BLOG.md](MEDICINE_DRUG_PAGES_AND_BLOG.md) — страницы препаратов `/drugs/<slug>` (бренд и все формы), блог, отчёт по товарам со спросом, микроразметка;
- [BRAND_PAGE_PERFORMANCE.md](BRAND_PAGE_PERFORMANCE.md) — скорость страницы бренда: замеры, детоаст `external_data`, частичные индексы 0217, `view=card`;
- [CATALOG_MAINTENANCE_COMMANDS.md](CATALOG_MAINTENANCE_COMMANDS.md) — битые медиа (`repair_broken_media`), бренды производителей лекарств/БАДов, доменные записи прежнего типа после смены типа товара (`retire_stale_domain_records`), ложные зачёркнутые цены (`clear_heuristic_old_prices`), названия LC Waikiki (`repair_lcw_names`);
- [CATEGORY_MARKUP_INHERITANCE.md](CATEGORY_MARKUP_INHERITANCE.md) — наследование товарной наценки: бренд → категория → родитель → глобальная;
- [brand-counts-cache.md](brand-counts-cache.md) — счётчики товаров брендов: снимок в кэше, Beat раз в 60 с;
- [ANALYTICS_EVENTS.md](ANALYTICS_EVENTS.md) — согласие, события GA4/Метрики и цели, как проверять;
- [HYDRATION_ERRORS_GUIDE.md](HYDRATION_ERRORS_GUIDE.md) — диагностика hydration;
- [TZ_SEO_PERF_FIXES.md](TZ_SEO_PERF_FIXES.md) — архивное ТЗ и отчёт SEO/performance от 2026-06-12;
- [frontend/LOCALIZATION_GUIDE.md](../frontend/LOCALIZATION_GUIDE.md) — локализация frontend;
- [frontend/FRONTEND-IMPROVEMENTS.md](../frontend/FRONTEND-IMPROVEMENTS.md) — накопленные frontend-идеи, не текущий release plan.

### Заказы, платежи и коммуникации

- [CRYPTO_PAYMENTS.md](../CRYPTO_PAYMENTS.md) — CoinRemitter и жизненный цикл криптоинвойса;
- [notifications-and-receipts.md](notifications-and-receipts.md) — каналы уведомлений и PDF-чеки;
- [CART_REMINDERS.md](CART_REMINDERS.md) — напоминания о неотправленном Списке заявки: включение в админке, кому и когда, отписка, журнал;
- [FEEDBACK_TRANSLATIONS.md](FEEDBACK_TRANSLATIONS.md) — переводы отзывов и вопросов: где заполнять в админке;
- [backend/apps/users/AUTHENTICATION.md](../backend/apps/users/AUTHENTICATION.md) — способы входа, JWT, лимиты частоты, Google/VK/Telegram;
- [SOCIAL_AUTH_PRODUCTION.md](SOCIAL_AUTH_PRODUCTION.md) — production OAuth/social auth;
- [DUPLICATE_MODERATION_GUIDE.md](../DUPLICATE_MODERATION_GUIDE.md) — модерация дублей.

### AI, рекомендации и фоновые задачи

- [AI_GUIDE.md](../AI_GUIDE.md) — основной AI workflow;
- [AI_RUNS_ADMIN_GUIDE.md](AI_RUNS_ADMIN_GUIDE.md) — пошагово: массовый AI-прогон, обслуживание и перевод абзацев инструкций (Batch API) кнопками в админке;
- [MEDICINE_PARAGRAPH_SHIFT_2026-10-20.md](MEDICINE_PARAGRAPH_SHIFT_2026-10-20.md) — сдвинутые переводы в памяти абзацев инструкций: правила без LLM, цифры, `medicine_paragraph_audit` и порядок действий на проде;
- [MEDICINE_TRANSLATION_KNOWLEDGE_BASE.md](MEDICINE_TRANSLATION_KNOWLEDGE_BASE.md) — база переводов инструкций TR/RU/EN (память, словарь веществ, стандартные фразы, глоссарий), проверка памяти агентами Haiku 23.10.2026, словари МНН и брендов и замена строк на сайте 24.10.2026 и как базой пользуются новые лекарства;
- [SEO_MEDICINES.md](SEO_MEDICINES.md) — SEO карточек лекарств кодом: правила, из чего собирается, как менять надёжно;
- [CONTROLLED_SUBSTANCES.md](CONTROLLED_SUBSTANCES.md) — препараты, запрещённые или ограниченные к ввозу в РФ, KZ, UZ: справочник, отметка, админка, что проверить юристу;
- [AI_MODULE_OVERVIEW.md](../AI_MODULE_OVERVIEW.md) — состав AI-модуля;
- [AI_TEMPLATES.md](../AI_TEMPLATES.md) — AI-шаблоны;
- [AI_TEST_COMMANDS.md](../AI_TEST_COMMANDS.md) и [AI_QUICK_TEST.md](../AI_QUICK_TEST.md) — специализированные проверки;
- [PERSONALIZED_RECOMMENDATIONS.md](PERSONALIZED_RECOMMENDATIONS.md) — что требуется до включения настоящей персонализации;
- [ml_service/README.md](../ml_service/README.md) — заглушка отдельного ML-сервиса (не используется, backend работает с LLM/Qdrant напрямую);
- [CELERY_TASKS.md](../CELERY_TASKS.md) — очереди и расписание Celery.

AI и VAPI HTTP API являются административными и требуют staff-пользователя. Наличие документа с примером endpoint не означает публичный доступ.

### Импорт и парсеры

- [SCRAPERS_GUIDE.md](../SCRAPERS_GUIDE.md) — общий workflow парсеров;
- [PARSER_MODES.md](PARSER_MODES.md) — режимы «товар / категория / весь сайт» и как их запускать;
- [MEDICINE_PARSER_CATEGORIES.md](MEDICINE_PARSER_CATEGORIES.md) — как парсер выбирает категорию медикамента;
- [PARSER_CATALOG_AUDIT_2026-09-14.md](PARSER_CATALOG_AUDIT_2026-09-14.md) — проверка парсеров 14.09 и перенос исправлений в main 17.10;
- [INSTAGRAM_PARSER_GUIDE.md](../INSTAGRAM_PARSER_GUIDE.md) и [quickstart](../backend/INSTAGRAM_PARSER_QUICKSTART.md);
- [PARSER_R2_GUIDE.md](../PARSER_R2_GUIDE.md) — storage для результатов парсинга;
- [UMMALAND_PARSER_GUIDE.md](../UMMALAND_PARSER_GUIDE.md) — доменный parser guide.

Любой реальный запуск парсера сначала выполняйте в dry-run/ограниченном режиме: внешние сайты и их правила меняются независимо от репозитория.

### Валюты и администрирование

- [CURRENCY_ADMIN_GUIDE.md](../CURRENCY_ADMIN_GUIDE.md) — ориентир по работе через admin; перед изменением данных сверять модели и поля с текущим кодом;
- [CATALOG_ADMIN_ACTIONS_GUIDE.md](../CATALOG_ADMIN_ACTIONS_GUIDE.md), [CATEGORY_ADMIN_GUIDE.md](../CATEGORY_ADMIN_GUIDE.md), [ADMIN_BOOKS_ANALYSIS.md](../ADMIN_BOOKS_ANALYSIS.md).

## Исторические и проектные материалы

Следующие файлы фиксируют анализ или состояние на момент конкретной работы. Они не заменяют текущий roadmap и могут ссылаться на старые версии/архитектуру:

- [ADMIN_IMPROVEMENTS_SUMMARY.md](../ADMIN_IMPROVEMENTS_SUMMARY.md);
- [CATALOG_REFACTORING_STATUS.md](../CATALOG_REFACTORING_STATUS.md);
- [CATEGORY_ARCHITECTURE_ANALYSIS.md](../CATEGORY_ARCHITECTURE_ANALYSIS.md);
- [CURRENCY_CONVERSION_PLAN.md](../CURRENCY_CONVERSION_PLAN.md);
- [CURRENCY_SYSTEM_GUIDE.md](../CURRENCY_SYSTEM_GUIDE.md), [CURRENCY_DEPLOYMENT_GUIDE.md](../CURRENCY_DEPLOYMENT_GUIDE.md) и [deployment checklist](../CURRENCY_DEPLOYMENT_CHECKLIST.md) — явно архивные, команды не исполнять без пересверки;
- [CURRENCY_SYSTEM_READY.md](../CURRENCY_SYSTEM_READY.md);
- [INSTAGRAM_PARSER_IMPLEMENTATION.md](../INSTAGRAM_PARSER_IMPLEMENTATION.md);
- [INSTAGRAM_PARSER_SUMMARY.md](../INSTAGRAM_PARSER_SUMMARY.md);
- [REFACTORING_PLAN.md](../REFACTORING_PLAN.md).

Информация о Next.js 14, Django 4.2, 18 категориях, OpenSearch, Coinbase, ЮKassa/CloudPayments, Grafana или ELK в старых материалах не описывает текущий baseline автоматически. Подтверждённый baseline приведён в [README.md](../README.md).

## Правила обновления документации

- новая документация создаётся в `docs/`, если это не главный README или специальный tool-owned файл;
- команды должны указывать контекст: host, Poetry, npm или Docker Compose;
- опасные операции (`down -v`, очистка volumes, массовый backfill) сопровождаются описанием потери данных, backup и dry-run;
- изменение permission, env, route, queue или версии зависимости обновляет связанный документ в том же PR;
- выполненный тест описывается точной командой; Docker/production проверка не заявляется, если она не запускалась;
- исторические отчёты не переписываются как будто они были актуальными всегда — для них указывается дата и ссылка на текущий roadmap.
