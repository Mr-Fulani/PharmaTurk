"""Три режима запуска: товар по ссылке, вся категория, весь сайт."""

from unittest.mock import patch

import pytest

from apps.catalog.models import Category
from apps.scrapers.admin import SiteScraperTaskForm
from apps.scrapers.base.offers import MalformedOfferResponse
from apps.scrapers.base.scraper import CategoryPageNotFoundError
from apps.scrapers.models import CategoryMapping, ScraperConfig, ScrapingSession, SiteScraperTask
from apps.scrapers.parsers.ilacfiyati import IlacFiyatiParser
from apps.scrapers.parsers.ummaland import UmmalandParser
from apps.scrapers.services import ScraperIntegrationService
from apps.scrapers.tasks import run_scraper_task

pytestmark = pytest.mark.django_db

CATEGORIES = [
    {"name": "Платья", "url": "https://site.test/c/dresses"},
    {"name": "Обувь", "url": "https://site.test/c/shoes"},
]


class _SiteParser:
    """Парсер-заглушка: две категории, без сети."""

    SUPPORTS_PAGE_CHUNKING = False
    categories = CATEGORIES

    def __init__(self, **kwargs):
        self.delay_range = (0, 0)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def configure_request_identity(self, **kwargs):
        return None

    def parse_categories(self):
        return list(self.categories)


def _site_task(**overrides):
    category, _ = Category.objects.get_or_create(slug="modes-root", defaults={"name": "Корень"})
    config = ScraperConfig.objects.create(
        name="modes-site", parser_class="fake-site", base_url="https://site.test",
        default_category=category,
    )
    values = dict(scraper_config=config, task_type="site", max_pages=1, max_products=100, status="running")
    values.update(overrides)
    return SiteScraperTask.objects.create(**values), config


def _run_chunk(task, config, *, fail_url=None, start_url="", error=None):
    calls = []

    def fake_run_scraper(self, **kwargs):
        calls.append((kwargs["start_url"], kwargs.get("target_category")))
        if kwargs["start_url"] == fail_url:
            raise error or RuntimeError("категория недоступна")
        return ScrapingSession.objects.create(
            scraper_config=config, status="completed", products_found=2, products_created=2,
            start_url=kwargs["start_url"],
        )

    with patch("apps.scrapers.tasks.get_parser", lambda name: _SiteParser), \
            patch.object(ScraperIntegrationService, "run_scraper", fake_run_scraper), \
            patch("apps.scrapers.tasks.run_scraper_task.apply_async") as enqueue:
        enqueue.return_value.id = "next-chunk"
        result = run_scraper_task.apply(
            args=[config.id],
            kwargs={"start_url": start_url, "site_task_id": task.id, "site_run_token": str(task.run_token or "")},
        ).get()
    task.refresh_from_db()
    return result, calls, enqueue


def test_site_task_discovers_categories_and_runs_the_first_one():
    task, config = _site_task()

    _result, calls, enqueue = _run_chunk(task, config)

    assert task.site_categories == CATEGORIES
    assert calls == [("https://site.test/c/dresses", None)]
    # Первая категория кончилась — следующий чанк идёт по второй.
    assert task.site_category_index == 1
    assert enqueue.call_args.kwargs["kwargs"]["start_url"] == "https://site.test/c/shoes"
    assert enqueue.call_args.kwargs["kwargs"]["start_page"] == 1
    assert task.status == "running"


def test_site_task_completes_after_the_last_category():
    task, config = _site_task(site_categories=CATEGORIES, site_category_index=1)

    _result, calls, enqueue = _run_chunk(task, config, start_url="https://site.test")

    assert calls == [("https://site.test/c/shoes", None)]
    assert not enqueue.called
    assert task.status == "completed"


def test_site_task_uses_category_mapping_when_task_has_no_target():
    task, config = _site_task(site_categories=CATEGORIES)
    shoes, _ = Category.objects.get_or_create(slug="modes-shoes", defaults={"name": "Обувь"})
    CategoryMapping.objects.create(
        scraper_config=config, internal_category=shoes, external_category_name="Платья",
        external_category_url="https://site.test/c/dresses",
    )

    _result, calls, _enqueue = _run_chunk(task, config)

    assert calls == [("https://site.test/c/dresses", shoes)]


def test_failed_category_does_not_stop_the_whole_site(monkeypatch):
    task, config = _site_task(site_categories=CATEGORIES)
    monkeypatch.setattr(run_scraper_task, "max_retries", 0)

    result, _calls, enqueue = _run_chunk(task, config, fail_url="https://site.test/c/dresses")

    assert result["continued_with_next_category"] is True
    assert enqueue.call_args.kwargs["kwargs"]["start_url"] == "https://site.test/c/shoes"
    assert task.status == "running"
    assert task.errors_count == 1


def test_site_task_without_categories_fails_clearly(monkeypatch):
    task, config = _site_task()
    monkeypatch.setattr(_SiteParser, "categories", [])
    monkeypatch.setattr(run_scraper_task, "max_retries", 0)

    _result, calls, _enqueue = _run_chunk(task, config)

    assert calls == []
    assert task.status == "failed"
    assert "не нашёл ни одной категории" in task.error_message


def test_catalog_task_requires_a_url():
    task, config = _site_task()
    form = SiteScraperTaskForm(data={
        "scraper_config": config.pk, "task_type": "catalog", "start_url": "",
        "max_pages": 1, "max_products": 10, "max_images_per_product": 5, "status": "pending",
        "gender": "",
    })
    assert not form.is_valid()
    assert "start_url" in form.errors


def test_ilacfiyati_whole_site_is_both_root_catalogs():
    categories = IlacFiyatiParser(base_url="https://ilacfiyati.com").parse_categories()
    assert [row["url"] for row in categories] == [
        "https://ilacfiyati.com/ilaclar",
        "https://ilacfiyati.com/takviye-edici-gida",
    ]
    assert all(IlacFiyatiParser.is_category_url(row["url"]) for row in categories)


def test_ummaland_whole_site_uses_root_store_categories(monkeypatch):
    parser = UmmalandParser("https://umma-land.com")

    class _Response:
        status_code = 200
        url = parser.CATEGORIES_API_URL

        def raise_for_status(self):
            return None

        def json(self):
            base = "https://umma-land.com/product-category"
            return [
                {"id": 16, "slug": "books", "name": "Книги", "parent": 0, "count": 100, "permalink": f"{base}/books"},
                {"id": 20, "slug": "holiday", "name": "Праздники", "parent": 0, "count": 350, "permalink": f"{base}/holiday"},
                {"id": 22, "slug": "hudozhestvennye", "name": "Худ.", "parent": 16, "count": 49, "permalink": f"{base}/books/hudozhestvennye"},
                {"id": 37, "slug": "new", "name": "Новинки", "parent": 0, "count": 109, "permalink": f"{base}/new"},
                {"id": 99, "slug": "empty", "name": "Пусто", "parent": 0, "count": 0, "permalink": f"{base}/empty"},
            ]

    monkeypatch.setattr(parser.client, "get", lambda url, **kwargs: _Response())

    assert [row["name"] for row in parser.parse_categories()] == ["Книги", "Праздники"]


def test_ummaland_category_goes_to_the_end_in_chunks(monkeypatch):
    parser = UmmalandParser("https://umma-land.com")
    items = [{"id": i, "name": f"Книга {i}", "link": f"https://umma-land.com/product/b{i}", "price": "100", "in_stock": True} for i in range(45)]
    monkeypatch.setattr(parser, "_get_category_id", lambda url: 16)
    monkeypatch.setattr(parser, "_fetch_products_from_api", lambda category_id: items)
    monkeypatch.setattr(parser, "parse_product_detail", lambda url: parser._parse_api_item({"id": 0, "name": "x", "link": url, "price": "100", "in_stock": True}))
    url = "https://umma-land.com/product-category/books"

    first = list(parser.parse_product_list(url, max_pages=1, start_page=1))
    assert len(first) == 20 and parser.has_more_pages is True
    last = list(parser.parse_product_list(url, max_pages=1, start_page=3))
    assert len(last) == 5 and parser.has_more_pages is False
    assert UmmalandParser.supports_page_chunking_for_url(url) is True
    assert UmmalandParser.supports_page_chunking_for_url("https://umma-land.com/product/b1") is False


@pytest.mark.parametrize(
    "error",
    [
        MalformedOfferResponse("Massimo Dutti: в ответе productsArray нет карточек с цветами"),
        CategoryPageNotFoundError("LCW: страница категории не найдена"),
    ],
)
def test_empty_or_missing_category_is_skipped_without_retries(error):
    """Проба на проде 21.10: лукбук Massimo Dutti без карточек повторялся
    4 раза через прокси, прежде чем обход шёл к следующей категории."""
    task, config = _site_task(site_categories=CATEGORIES)

    result, calls, enqueue = _run_chunk(task, config, fail_url="https://site.test/c/dresses", error=error)

    assert [url for url, _ in calls] == ["https://site.test/c/dresses"]
    assert result["continued_with_next_category"] is True
    assert enqueue.call_args.kwargs["kwargs"]["start_url"] == "https://site.test/c/shoes"
    assert task.errors_count == 1
