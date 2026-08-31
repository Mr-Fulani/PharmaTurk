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
| [ROADMAP.md](ROADMAP.md) | текущий backlog и отделённый snapshot июня 2026 | актуализирован 2026-08-21 |
| [TECH_DEBT.md](TECH_DEBT.md) | реестр подтверждённого открытого технического долга | актуализирован 2026-08-22 |
| [SOURCE_OFFER_CART_VERIFICATION_PLAN.md](SOURCE_OFFER_CART_VERIFICATION_PLAN.md) | рабочий план проверки цены и наличия первоисточника в корзине и checkout | активен с 2026-08-27 |
| [PRODUCT_CARD_SOURCE_REFRESH_PLAN.md](PRODUCT_CARD_SOURCE_REFRESH_PLAN.md) | план и статус обновления цены/вариантов спарсенной карточки при открытии | активен с 2026-08-29 |
| [SOURCE_OFFER_OPERATIONS_RUNBOOK.md](SOURCE_OFFER_OPERATIONS_RUNBOOK.md) | rollout, метрики, alerting и безопасный повтор source-offer checks | актуализирован 2026-08-31 |
| [PAID_WEB_ACCESS_SERVICES.md](PAID_WEB_ACCESS_SERVICES.md) | Bright Data proxy/Web Unlocker: тарифы, бюджет, возможности и безопасное переиспользование | актуализирован 2026-08-31 |
| [SOURCE_OFFER_CART_API.md](SOURCE_OFFER_CART_API.md) | Cart API: verification fields, issue codes, 409/503 и действия клиента | актуализирован 2026-08-27 |
| [DEPLOY.md](../DEPLOY.md) | production deployment и rollback | актуализирован и проверен 2026-08-21 |
| [DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md) | правила SEO, backend/frontend и e-commerce | актуализирован 2026-08-09 |

## Доменная документация

### Каталог, SEO и frontend

- [CATALOG_FAVORITES_PROXY_MEDIA.md](CATALOG_FAVORITES_PROXY_MEDIA.md) — доменные id, избранное, R2 и proxy-media;
- [FURNITURE_ATTRIBUTES_BACKFILL.md](FURNITURE_ATTRIBUTES_BACKFILL.md) — безопасный backfill характеристик мебели;
- [HYDRATION_ERRORS_GUIDE.md](HYDRATION_ERRORS_GUIDE.md) — диагностика hydration;
- [TZ_SEO_PERF_FIXES.md](TZ_SEO_PERF_FIXES.md) — архивное ТЗ и отчёт SEO/performance от 2026-06-12;
- [frontend/LOCALIZATION_GUIDE.md](../frontend/LOCALIZATION_GUIDE.md) — локализация frontend;
- [frontend/FRONTEND-IMPROVEMENTS.md](../frontend/FRONTEND-IMPROVEMENTS.md) — накопленные frontend-идеи, не текущий release plan.

### Заказы, платежи и коммуникации

- [CRYPTO_PAYMENTS.md](../CRYPTO_PAYMENTS.md) — CoinRemitter и жизненный цикл криптоинвойса;
- [notifications-and-receipts.md](notifications-and-receipts.md) — каналы уведомлений и PDF-чеки;
- [SOCIAL_AUTH_PRODUCTION.md](SOCIAL_AUTH_PRODUCTION.md) — production OAuth/social auth;
- [DUPLICATE_MODERATION_GUIDE.md](../DUPLICATE_MODERATION_GUIDE.md) — модерация дублей.

### AI, рекомендации и фоновые задачи

- [AI_GUIDE.md](../AI_GUIDE.md) — основной AI workflow;
- [AI_MODULE_OVERVIEW.md](../AI_MODULE_OVERVIEW.md) — состав AI-модуля;
- [AI_TEMPLATES.md](../AI_TEMPLATES.md) — AI-шаблоны;
- [AI_TEST_COMMANDS.md](../AI_TEST_COMMANDS.md) и [AI_QUICK_TEST.md](../AI_QUICK_TEST.md) — специализированные проверки;
- [PERSONALIZED_RECOMMENDATIONS.md](PERSONALIZED_RECOMMENDATIONS.md) — что требуется до включения настоящей персонализации;
- [CELERY_TASKS.md](../CELERY_TASKS.md) — очереди и расписание Celery.

AI и VAPI HTTP API являются административными и требуют staff-пользователя. Наличие документа с примером endpoint не означает публичный доступ.

### Импорт и парсеры

- [SCRAPERS_GUIDE.md](../SCRAPERS_GUIDE.md) — общий workflow парсеров;
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
