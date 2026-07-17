import httpx
import instaloader
import pytest

from apps.catalog.services import IkeaService
from apps.http_errors import ExternalAccessBlockedError
from apps.scrapers.parsers.ilacabak import IlacabakParser
from apps.scrapers.parsers.ilacfiyati import IlacFiyatiParser
from apps.scrapers.parsers.instagram import InstagramParser
from apps.scrapers.parsers.lcw import LcwParser
from apps.scrapers.parsers.ummaland import UmmalandParser


def _httpx_response(status_code: int, url: str = "https://example.com/catalog"):
    return httpx.Response(
        status_code,
        request=httpx.Request("GET", url),
    )


@pytest.mark.parametrize("status_code", [401, 403, 407])
def test_base_scraper_raises_for_access_denied(monkeypatch, status_code):
    parser = LcwParser(base_url="https://www.lcw.com")
    monkeypatch.setattr(
        parser.client,
        "get",
        lambda *args, **kwargs: _httpx_response(status_code),
    )

    with pytest.raises(ExternalAccessBlockedError) as exc_info:
        parser._make_request("https://example.com/catalog")

    assert exc_info.value.status_code == status_code


def test_base_scraper_raises_transport_error_after_retries(monkeypatch):
    parser = LcwParser(base_url="https://www.lcw.com", max_retries=0)

    def fail(*args, **kwargs):
        raise httpx.ConnectError("proxy unavailable")

    monkeypatch.setattr(parser.client, "get", fail)

    with pytest.raises(httpx.ConnectError, match="proxy unavailable"):
        parser._make_request("https://example.com/catalog")


def test_base_scraper_keeps_404_as_not_found(monkeypatch):
    parser = LcwParser(base_url="https://www.lcw.com")
    monkeypatch.setattr(
        parser.client,
        "get",
        lambda *args, **kwargs: _httpx_response(404),
    )

    assert parser._make_request("https://example.com/missing") is None


@pytest.mark.parametrize(
    ("parser", "run"),
    [
        (
            IlacabakParser(),
            lambda parser: parser.parse_product_list("https://ilacabak.com/category", max_pages=1),
        ),
        (
            IlacFiyatiParser(base_url="https://www.ilacfiyati.com"),
            lambda parser: list(
                parser.parse_product_list("https://www.ilacfiyati.com/ilaclar", max_pages=1)
            ),
        ),
        (
            UmmalandParser(base_url="https://umma-land.com"),
            lambda parser: parser.parse_product_list(
                "https://umma-land.com/product-category/books", max_pages=1
            ),
        ),
    ],
)
def test_parsers_do_not_swallow_common_access_error(monkeypatch, parser, run):
    error = ExternalAccessBlockedError(
        source=parser.get_name(),
        status_code=403,
        url=parser.base_url,
    )
    monkeypatch.setattr(
        parser,
        "_make_request",
        lambda *args, **kwargs: (_ for _ in ()).throw(error),
    )

    with pytest.raises(ExternalAccessBlockedError):
        run(parser)


def test_ummaland_api_does_not_swallow_403(monkeypatch):
    parser = UmmalandParser(base_url="https://umma-land.com")
    response = _httpx_response(403, parser.API_URL)
    monkeypatch.setattr(parser.client, "post", lambda *args, **kwargs: response)

    with pytest.raises(ExternalAccessBlockedError, match="HTTP 403"):
        parser._fetch_products_from_api(10)


def test_ummaland_api_does_not_turn_500_into_empty_catalog(monkeypatch):
    parser = UmmalandParser(base_url="https://umma-land.com")
    response = _httpx_response(500, parser.API_URL)
    monkeypatch.setattr(parser.client, "post", lambda *args, **kwargs: response)

    with pytest.raises(httpx.HTTPStatusError):
        parser._fetch_products_from_api(10)


def test_ummaland_missing_category_id_is_a_task_error(monkeypatch):
    parser = UmmalandParser(base_url="https://umma-land.com")
    monkeypatch.setattr(parser, "_get_category_id", lambda url: None)

    with pytest.raises(RuntimeError, match="не удалось найти ID категории"):
        parser.parse_product_list(
            "https://umma-land.com/product-category/books",
            max_pages=1,
        )


@pytest.mark.parametrize("method_name", ["fetch_item_details", "search_items"])
def test_ikea_api_does_not_swallow_403(monkeypatch, method_name):
    service = IkeaService()
    response = _httpx_response(403, "https://frontendapi.ikea.com.tr/api/test")
    monkeypatch.setattr(service.client, "get", lambda *args, **kwargs: response)

    with pytest.raises(ExternalAccessBlockedError, match="HTTP 403"):
        if method_name == "fetch_item_details":
            service.fetch_item_details("80275887")
        else:
            service.search_items(query="kallax")


def test_instagram_structured_403_becomes_common_access_error(monkeypatch):
    parser = InstagramParser()

    def forbidden(*args, **kwargs):
        raise instaloader.exceptions.QueryReturnedForbiddenException("HTTP 403")

    monkeypatch.setattr(instaloader.Profile, "from_username", forbidden)

    with pytest.raises(ExternalAccessBlockedError) as exc_info:
        parser._parse_profile("test_profile", max_posts=1)

    assert exc_info.value.status_code == 403
