# Management-команды: справочник

Проверено по коду: 2026-10-22. Здесь только команды, которых нет в тематических
документах; остальные — по ссылкам ниже. Код команд —
`backend/apps/<приложение>/management/commands/<команда>.py`.

## Как запускать

На проде — из корня проекта на сервере, compose-проект `mudaroba` (как в
[FURNITURE_ATTRIBUTES_BACKFILL.md](FURNITURE_ATTRIBUTES_BACKFILL.md)):

```bash
docker compose -p mudaroba -f docker-compose.yml -f docker-compose.prod.yml \
  exec -T backend poetry run python manage.py <команда> [флаги]

# то же короче, по имени контейнера (как в PROD_DB_MAINTENANCE.md)
docker exec mudaroba-backend-1 poetry run python manage.py <команда> [флаги]
```

`poetry run` обязателен: зависимости стоят в `/app/.venv`, системный `python` их не
видит. Локально — `docker compose exec backend poetry run python manage.py …`.

Перед командой, которая пишет в БД: сначала dry-run или отчёт, затем `pg_dump`
(пример — [PROD_DB_MAINTENANCE.md](PROD_DB_MAINTENANCE.md)). Команды, которые ходят на
внешние сайты через платный прокси, — только с согласия владельца
([PAID_WEB_ACCESS_SERVICES.md](PAID_WEB_ACCESS_SERVICES.md)).

## Где описаны остальные команды

| Документ | Команды |
| --- | --- |
| [CATALOG_MAINTENANCE_COMMANDS.md](CATALOG_MAINTENANCE_COMMANDS.md) | `repair_broken_media`, `assign_manufacturer_brands`, `repair_flo_brands`, `clear_heuristic_old_prices`, `repair_lcw_names`, `retire_stale_domain_records` |
| [CONTROLLED_SUBSTANCES.md](CONTROLLED_SUBSTANCES.md) | `refresh_import_restrictions` |
| [SOURCE_OFFER_OPERATIONS_RUNBOOK.md](SOURCE_OFFER_OPERATIONS_RUNBOOK.md) | `audit_source_offer_rollout`, `discover_supplement_stock_offers` |
| [FURNITURE_ATTRIBUTES_BACKFILL.md](FURNITURE_ATTRIBUTES_BACKFILL.md) | `backfill_furniture_attributes` |
| [AI_GUIDE.md](../AI_GUIDE.md) | `ai_enqueue`, `retry_ai_titles`, `close_resolved_ai_moderation`, `medicine_paragraph_audit`, `medicine_paragraph_batch`, `medicine_reference_coverage`, `medicine_source_names`, `translate_medicine_inn`, `medicine_refresh_code_fields`, `benchmark_ai` |
| [AI_MODULE_OVERVIEW.md](../AI_MODULE_OVERVIEW.md) | `setup_ai_rag` = `init_qdrant` + `sync_categories` + `import_templates` |
| [AI_TEMPLATES.md](../AI_TEMPLATES.md) | `seed_ai_category_instructions` |
| [CELERY_TASKS.md](../CELERY_TASKS.md) | `sync_product_vectors`, `clear_similar_cache` |
| [DB_BACKUP.md](DB_BACKUP.md) | `db_backup` (запускается в `celeryworker`) |
| [DEPLOY.md](../DEPLOY.md) | `set_telegram_webhook`, `reconcile_coinremitter`, `cleanup_legacy_receipts` |
| [CURRENCY_SYSTEM_GUIDE.md](../CURRENCY_SYSTEM_GUIDE.md) | `update_product_prices` |
| [README-DEV.md](../README-DEV.md) | `seed_catalog_data`, `load_initial_pages` |
| [SCRAPERS_GUIDE.md](../SCRAPERS_GUIDE.md) | `heal_parsed_gallery_media` |
| [UMMALAND_PARSER_GUIDE.md](../UMMALAND_PARSER_GUIDE.md) | `run_scraper` |
| [INSTAGRAM_PARSER_GUIDE.md](../INSTAGRAM_PARSER_GUIDE.md), [INSTAGRAM_PARSER_IMPLEMENTATION.md](../INSTAGRAM_PARSER_IMPLEMENTATION.md) | `run_instagram_scraper`, `init_instagram_scraper` |

## catalog

| Команда | Что делает, флаги | На проде |
| --- | --- | --- |
| `assign_supplement_subcategories` | БАДы из корня «БАДы» раскладывает по подкатегориям по турецкому названию (`external_data.source_name`, иначе `name`; правило — `apps/catalog/supplement_taxonomy.py`, без LLM); если турецкое название — только бренд, по RU-названию карточки (`supplement_category_slug_ru`, с 26.10.2026); нераспознанные оставляет в корне. С 27.10.2026 товары корня и разделов раскладывает дальше по подкатегориям-веществам («Минералы» → «Магний», `supplement_substance_slug`), комплексы оставляет в разделе, а пустые подкатегории из `RETIRED_SUBCATEGORY_SLUGS` выключает (с товарами — не трогает и предупреждает). Пишет доменную запись и базовый `Product` через `update()` (slug не меняется). Отказывается, если у подкатегории наценка не совпадает с корнем (изменились бы цены). Отчёт: сколько в какую подкатегорию, примеры, CSV (`--report`, по умолчанию `/tmp/supplement_subcategories_*.csv`) с `old_category_id` — он же файл отката. Dry-run по умолчанию, `--apply` | пишет только с `--apply`; перед ним — бэкап строк `catalog_product`/`catalog_supplementproduct` |
| `audit_dynamic_attribute_keys` | Сверяет category-привязки динамических атрибутов (`GlobalAttributeKey`) с `ECOMMERCE_ATTRIBUTES`: ключи без категорий и расхождения. `--only-unbound` — только ключи без привязок; `--sync` — добавить недостающие привязки (лишние не снимает) | без `--sync` — только чтение |
| `backfill_category_seo` | Заполняет пустые meta/OG-поля категорий значениями по умолчанию, заполненные не трогает. `--dry-run` — показать без сохранения | пишет в БД; сначала `--dry-run` |
| `category_landing_seo` | SEO разделов (H1, title, description, SEO-текст RU/EN) через Claude: `generate` пишет черновик в JSON, `apply` — в пустые поля переводов с бэкапом ([CATEGORY_LANDING_SEO.md](CATEGORY_LANDING_SEO.md)) | `generate` — платный запрос к Claude, БД не меняет; `apply` пишет в БД, сначала `--dry-run` |
| `backfill_source_offers` | Создаёт `ProductSourceOffer` из сохранённой истории парсинга (`external_url`, `external_data.scraped_sources`), без запросов к источникам; идемпотентна. Dry-run по умолчанию; `--apply`, `--source <parser key>`, `--start-id`, `--limit` (1..10000, 1000), `--batch-size` (200). Шаг 2 rollout в [runbook](SOURCE_OFFER_OPERATIONS_RUNBOOK.md) | пишет только с `--apply` |
| `download_all_media` | Скачивает в R2 внешние картинки товаров, отзывов, услуг, категорий и брендов; уже лежащие в R2 пропускает. `--only products\|main_images\|testimonials\|services\|categories\|brands\|all`, `--limit`, `--force` (перекачать), `--sync-internal` (URL уже на нашем CDN — проставить путь в файловое поле без скачивания), `--dry-run` | пишет в R2 и БД; сначала `--dry-run`. Битые ссылки на R2 чинит `repair_broken_media` |
| `download_banner_media` | То же для медиа баннеров (`BannerMedia`: картинка, видео, GIF). `--banner-id`, `--force`, `--dry-run` | пишет в R2 и БД |
| `refresh_currency_margin_snapshots` | Пересчитывает `*_price_with_margin` в `ProductPrice`, `ProductVariantPrice`, `ServicePrice` и `Product.final_price_rub/usd` по текущим маржам валютных пар; курсы и базовые цены не трогает. То же делает задача `currency.refresh_margin_snapshots` после сохранения маржи в админке. Флагов нет | пишет в БД (все строки цен, одна транзакция) |
| `remap_flo_shoe_categories` | Обувь FLO из корня `shoes` раскладывает по `sandals`, `sneakers`, `home-shoes`, `boots`, `dress-shoes` по названию и URL (доменная запись и базовый `Product`). Новые товары парсер раскладывает тем же правилом. Dry-run по умолчанию, `--apply` | пишет только с `--apply` |
| `remap_ikea_categories` | Показывает и с `--apply` переносит товары IKEA в уверенно определённые подкатегории мебели; категории не создаёт и не удаляет (без нужных категорий `--apply` падает). `--limit`, `--show-all`. Категорию определяет `ikea_category_mapping.py`: точный тип товара (function/`furniture_type`) важнее категории API, а общий раздел запуска (`koltuklar`, `karyolalar`, `gardiroplar`, `sifonyerler`) — последний: с 27.10.2026 реечные днища уходят из «Кроватей» в «Основания кроватей», двухъярусные кровати и детские комоды SMÅSTAD — из «Гардеробов», диваны-кровати и POÄNG — из «Кресел» (в очереди модерации 27.10.2026 — 53 товара); раздел IKEA «bazalar» (MALM, TONSTAD, IDANÄS с подъёмным основанием) — в «Кровати с хранением» (`storage-beds`, решение владельца 27.10.2026); детский гардероб (`çocuk gardırobu`) — в «Детские шкафы», напольная вешалка — в «Вешалки и гардеробные», кухонные острова и рабочие столы IKEA — в «Кухонные столы» | пишет только с `--apply` |
| `seed_perfumery_brands` | Создаёт 46 брендов парфюмерии (`primary_category_slug=perfumery`). `update_or_create` по slug: у существующего бренда перезапишет название, описание, сайт и `is_active`. Флагов нет | пишет в БД; осторожно — перезапись описаний брендов |
| `sync_ikea_products` | Загружает товары IKEA TR по артикулам (`--item-codes A B …`) или поиску (`--search "…"`, `--limit` 10) и создаёт/обновляет `FurnitureProduct`. Штатный путь — парсер IKEA из админки ([PARSER_MODES.md](PARSER_MODES.md)) | пишет в БД, запросы к IKEA |
| `sync_vk_photos` | Загружает фото (до `--max-photos`, 5) и видео наших товаров в уже существующие товары ВК Маркета, сопоставляя по `external_id` из YML. `--offer-id`, `--category <slug>` (категория с подкатегориями), `--skip-video`, `--dry-run`. Из админки «Маппинги категорий ВК» запускается фоновой задачей `catalog.sync_vk_photos`, итог — в Telegram. Нужны `VK_YML_API`, `VK_USER_TOKEN`, `VK_GROUP_ID`; БД не меняет | меняет публичный ВК Маркет — только с согласия владельца, сначала `--dry-run` |
| `update_currency_rates` | Загружает курсы ЦБ РФ и Нацбанка Казахстана в `CurrencyRate`, пишет `CurrencyUpdateLog`. Её вызывает действие админки «Обновить выбранные курсы»; ежедневная задача `currency.update_rates` идёт через `CurrencyRateService`, не через неё. Флагов нет | пишет в БД |
| `migrate_media_hierarchy` | **Устарело.** Разовый перенос файлов R2 из `products/{leaf}/` в `products/{root}/…/{leaf}/` (2026-06-15); через пять дней раскладку заменила `migrate_product_media_layout`. `--dry-run`, `--limit` | не запускать |
| `migrate_product_media_layout` | **Устарело** — разовая миграция 2026-06-20. Переносит файлы R2 из старых папок `…/main\|gallery\|variants/` в одну папку на товар (`products/{категория}/{slug}/…`): copy → проверка → UPDATE без сигналов → delete. Новые загрузки уже идут в эту раскладку. `--dry-run`, `--limit` | только `--dry-run`, чтобы увидеть остатки |
| `reclassify_terminal_source_offer_errors` | **Устарело** — разовая (2026-09-04) для строк, записанных до исправления адаптеров LCW и Zara в том же коммите: offers с `last_error_code=option_not_found` и точным сообщением адаптера переводит в `out_of_stock` (LCW, размер) или `discontinued` (Zara, цвет), без запросов к источнику. Dry-run по умолчанию; `--apply`, `--source all\|lcw\|zara`, `--limit` (5000, до 10000) | повторный запуск безопасен, сначала без `--apply` |
| `update_productprice_currencies` | **Устарело** (январь 2026). Пересчитывает конвертированные цены строк `ProductPrice` в RUB/USD/KZT/EUR/TRY — без USDT и без `Product.final_price_*`. Штатно — `update_product_prices` (задача `currency.update_product_prices` ежедневно) и `refresh_currency_margin_snapshots`. `--batch-size` (50), `--dry-run` | не запускать |

### Тестовые данные (только локально)

Все команды ниже создают тестовые бренды, категории или товары в текущей базе. На
проде не запускать.

| Команда | Что создаёт |
| --- | --- |
| `create_test_data` | бренды, категории и товары одежды, обуви и электроники; категории создаются через `create()`, повторный запуск падает на уникальном slug |
| `create_medicine_test_data` | 10 медикаментов (`Product` без категории) и фарм-бренды |
| `create_turkish_brands` | турецкие бренды и тестовую одежду к ним |
| `seed_turkish_brands` | турецкие и мировые бренды с переводами (переводы перезаписывает) и примерные товары для витрин |
| `generate_test_products` | 1–3 товара `… [TEST]` в каждую листовую категорию: `--count` (2), `--clear` — удалить прежние `[TEST]`, `--dry-run` |

## ai

| Команда | Что делает, флаги | На проде |
| --- | --- | --- |
| `test_ai_books` | Создаёт 5 тестовых книг в категории `books-test` и прогоняет по ним AI-генерацию с `auto_apply=True`. Флагов нет | не запускать: тестовые товары и платные запросы OpenAI |

## recommendations

| Команда | Что делает, флаги | На проде |
| --- | --- | --- |
| `recsys_stats` | Покрытие доступных товаров векторами (`ProductVector`) и показы, клики, CTR и конверсия по алгоритмам из `RecommendationEvent`. Флагов нет | только чтение |

## scrapers

| Команда | Что делает, флаги | На проде |
| --- | --- | --- |
| `backend_release_plan` | Гейт сокращённого backend-релиза: падает, если есть задачи парсеров в `pending/running` или Celery-воркеры заняты или не отвечают; печатает JSON плана миграций и пропускает только добавление nullable UUID-поля в `SiteScraperTask`. Вручную не нужна — её вызывает `scripts/release/backend_release.py` через сервис `migrate` в read-only транзакции | только чтение |
| `ilacfiyati_changes_probe` | «Только посмотреть» для режима «Только изменения» IlacFiyati: проходит листинги лекарств и БАДов и sitemap, печатает, сколько карточек откроется, сколько товаров снимется с продажи, сколько запросов и часов против полного обхода. `--pages N` — по N страниц каждого листинга без sitemap; `--sample-cards N` — сколько карточек скачать для замера времени (5). Задержки и заголовки — из конфигурации IlacFiyati. Полный прогон на проде ≈ 1,3 ч ([PARSER_MODES.md](PARSER_MODES.md)) | только чтение БД; запросы к ilacfiyati.com |
| `review_gone_candidates` | Кандидаты на снятие с продажи из режима «Только изменения» при `SCRAPER_GONE_REQUIRES_REVIEW=true`: отчёт (по умолчанию, `--csv`), `--apply [--ids …]` — снять с продажи, `--clear --ids …` — убрать пометку. См. [PARSER_MODES.md](PARSER_MODES.md) | отчёт — только чтение; `--apply`/`--clear` — запись |
| `measure_listing_changes` | Замер точечного обхода «только посмотреть»: проходит списки категорий парсера (`flo`, `zara`, `lcw`, `ikea`, `ummaland`) без открытия карточек и без записи в базу; строки, запросы и байты списков, сколько карточек открыл бы обход (по `ListingSnapshot` или `--compare` файлу прошлого замера). `--url` (несколько) или `--categories N`, `--pages`, `--sample-cards N` (цена карточки и оценка полного/точечного обхода), `--save`, `--baseline`, `--use-proxy` (по умолчанию без прокси). См. [PARSER_MODES.md](PARSER_MODES.md) | только чтение; запросы к источнику, через прокси — только с согласия |
| `init_scrapers` | Создаёт `ScraperConfig` `ummaland`, `zara`, `lcw` и маппинг категории «Книги» для UmmaLand, если их нет (`get_or_create`, существующие не меняет). Для пустой локальной базы | на проде конфиги ведутся в админке — не нужна |
