# Ручные скрипты разработчика

Скрипты для локальной отладки. В Docker-образ не попадают (`backend/.dockerignore`),
поэтому на проде их нет. Запускать из каталога `backend/` на локальной базе.

| Скрипт | Что делает | Пишет в БД |
|---|---|---|
| `run_scraper_test.py <URL>` | Разбирает одну карточку Ummaland (`umma-land.com`) парсером `UmmalandParser`, печатает данные и сохраняет товар через `ScraperIntegrationService`, для книг показывает `BookProduct`. | Да: создаёт `ScraperConfig` «Test ummaland», `ScrapingSession` и товар |

```bash
poetry run python scripts/dev/run_scraper_test.py https://umma-land.com/product/<slug>/
```

Обычный запуск парсеров — `poetry run python manage.py run_scraper <имя> --url <URL>`
(см. `UMMALAND_PARSER_GUIDE.md`). Разовые диагностические скрипты сюда не складывать: по
правилам backend их удаляют до завершения задачи.
