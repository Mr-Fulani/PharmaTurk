from types import SimpleNamespace
from unittest.mock import patch

import instaloader
import pytest
from django.conf import settings
from django.core.management.base import CommandError

from apps.http_errors import ExternalAccessBlockedError
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.management.commands.run_instagram_scraper import Command
from apps.scrapers.models import ScraperConfig
from apps.scrapers.parsers.instagram import InstagramParser, InstagramSourceError


class _FeedResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _post(shortcode):
    return SimpleNamespace(shortcode=shortcode)


def _product(shortcode):
    return ScrapedProduct(
        name=f"Товар {shortcode}",
        description="Достаточно длинное описание товара",
        url=f"https://www.instagram.com/p/{shortcode}/",
        images=[f"https://cdn.example/{shortcode}.jpg"],
        external_id=shortcode,
        source="instagram",
    )


def _patch_product_conversion(monkeypatch, parser):
    monkeypatch.setattr(parser, "_parse_post", lambda post: _product(post.shortcode))


def test_business_profile_uses_mobile_feed_fallback(monkeypatch):
    parser = InstagramParser(max_retries=1)
    _patch_product_conversion(monkeypatch, parser)

    def broken_profile(*args, **kwargs):
        raise instaloader.exceptions.QueryReturnedBadRequestException(
            "HTTP 400 ig_business_category_subvertical"
        )

    monkeypatch.setattr(instaloader.Profile, "from_username", broken_profile)
    monkeypatch.setattr(
        parser.loader.context._session,
        "get",
        lambda *args, **kwargs: _FeedResponse(
            {
                "status": "ok",
                "items": [{"code": "POST1"}],
                "more_available": False,
                "user": {"username": "business.profile"},
            }
        ),
    )
    monkeypatch.setattr(
        instaloader.Post,
        "from_iphone_struct",
        lambda context, item: _post(item["code"]),
    )

    products = parser.parse_product_list(
        "https://www.instagram.com/business.profile/",
        max_pages=1,
    )

    assert [product.external_id for product in products] == ["POST1"]


def test_profile_fallback_continues_after_partial_graphql_page_without_duplicates(
    monkeypatch,
):
    parser = InstagramParser(max_retries=1)
    _patch_product_conversion(monkeypatch, parser)

    def primary_posts():
        yield _post("POST1")
        raise instaloader.exceptions.ConnectionException("HTTP 403 graphql/query")

    profile = SimpleNamespace(get_posts=primary_posts)
    monkeypatch.setattr(
        instaloader.Profile,
        "from_username",
        lambda *args, **kwargs: profile,
    )
    monkeypatch.setattr(
        parser.loader.context._session,
        "get",
        lambda *args, **kwargs: _FeedResponse(
            {
                "status": "ok",
                "items": [{"code": "POST1"}, {"code": "POST2"}],
                "more_available": False,
                "user": {"username": "business.profile"},
            }
        ),
    )
    monkeypatch.setattr(
        instaloader.Post,
        "from_iphone_struct",
        lambda context, item: _post(item["code"]),
    )

    products = parser.parse_product_list(
        "https://www.instagram.com/business.profile/",
        max_pages=2,
    )

    assert [product.external_id for product in products] == ["POST1", "POST2"]


def test_profile_fallback_retries_post_that_failed_in_primary_payload(monkeypatch):
    parser = InstagramParser(max_retries=1)
    attempts = 0

    def convert(post):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise instaloader.exceptions.QueryReturnedBadRequestException("HTTP 400")
        return _product(post.shortcode)

    monkeypatch.setattr(parser, "_parse_post", convert)
    monkeypatch.setattr(
        instaloader.Profile,
        "from_username",
        lambda *args, **kwargs: SimpleNamespace(get_posts=lambda: iter([_post("POST1")])),
    )
    monkeypatch.setattr(
        parser.loader.context._session,
        "get",
        lambda *args, **kwargs: _FeedResponse(
            {
                "status": "ok",
                "items": [{"code": "POST1"}],
                "more_available": False,
            }
        ),
    )
    monkeypatch.setattr(
        instaloader.Post,
        "from_iphone_struct",
        lambda context, item: _post(item["code"]),
    )

    products = parser.parse_product_list(
        "https://www.instagram.com/business.profile/",
        max_pages=1,
    )

    assert [product.external_id for product in products] == ["POST1"]
    assert attempts == 2


def test_instagram_api_failure_is_not_returned_as_empty_success(monkeypatch):
    parser = InstagramParser(max_retries=1)

    monkeypatch.setattr(
        instaloader.Profile,
        "from_username",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            instaloader.exceptions.QueryReturnedBadRequestException("HTTP 400")
        ),
    )
    monkeypatch.setattr(
        parser.loader.context._session,
        "get",
        lambda *args, **kwargs: _FeedResponse({}, status_code=500),
    )

    with pytest.raises(InstagramSourceError, match="fallback"):
        parser.parse_product_list(
            "https://www.instagram.com/business.profile/",
            max_pages=1,
        )


def test_post_connection_403_becomes_common_access_error(monkeypatch):
    parser = InstagramParser(max_retries=1)

    monkeypatch.setattr(
        instaloader.Post,
        "from_shortcode",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            instaloader.exceptions.ConnectionException("HTTP 403 graphql/query")
        ),
    )

    with pytest.raises(ExternalAccessBlockedError) as exc_info:
        parser.parse_product_detail("https://www.instagram.com/p/POST1/")

    assert exc_info.value.status_code == 403


def test_login_structured_403_keeps_common_access_error(monkeypatch):
    parser = InstagramParser(username="bot", password="secret")
    monkeypatch.setattr(
        parser.loader,
        "login",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            instaloader.exceptions.QueryReturnedForbiddenException("HTTP 403")
        ),
    )

    with pytest.raises(ExternalAccessBlockedError) as exc_info:
        parser._ensure_authenticated()

    assert exc_info.value.status_code == 403


def test_mobile_feed_metrics_do_not_trigger_graphql():
    class _FallbackPost:
        _iphone_struct_ = {"like_count": 11, "comment_count": 7}

        @property
        def likes(self):
            raise AssertionError("likes GraphQL request must not run")

        @property
        def comments(self):
            raise AssertionError("comments GraphQL request must not run")

    parser = InstagramParser()
    post = _FallbackPost()

    assert parser._post_metric(post, "likes", "like_count") == 11
    assert parser._post_metric(post, "comments", "comment_count") == 7


def test_scraper_identity_reaches_instaloader_transport(monkeypatch):
    monkeypatch.setattr(settings, "SCRAPER_PROXY_URL", "http://proxy.example:8080")
    parser = InstagramParser(use_proxy=True)

    parser.configure_request_identity(
        user_agent="Configured Instagram UA",
        headers={"X-Test-Header": "configured"},
        cookies={"sessionid": "configured-cookie"},
    )

    session = parser.loader.context._session
    assert session.proxies["https"] == "http://proxy.example:8080"
    assert session.headers["User-Agent"] == "Configured Instagram UA"
    assert session.headers["X-Test-Header"] == "configured"
    assert session.cookies.get("sessionid") == "configured-cookie"


@pytest.mark.parametrize(
    "value",
    [
        "https://www.instagram.com/",
        "https://www.instagram.com/explore/tags/books/",
        "https://example.com/profile/",
        "bad username",
    ],
)
def test_profile_username_validation_rejects_non_profile_values(value):
    parser = InstagramParser()

    with pytest.raises(ValueError):
        parser._extract_username(value)


def test_cli_autocreate_resolves_category_before_using_it(monkeypatch):
    command = Command()
    category = SimpleNamespace(name="Книги")
    config = SimpleNamespace(scraper_username="", scraper_password="")
    session = SimpleNamespace()
    created_kwargs = {}

    filter_result = SimpleNamespace(first=lambda: None)
    service = SimpleNamespace(run_scraper=lambda **kwargs: session)
    monkeypatch.setattr(command, "_resolve_category", lambda slug: category)
    monkeypatch.setattr(command, "_print_session_stats", lambda value: None)
    monkeypatch.setattr(
        "apps.scrapers.services.ScraperIntegrationService",
        lambda: service,
    )

    with (
        patch.object(ScraperConfig.objects, "filter", return_value=filter_result),
        patch.object(
            ScraperConfig.objects,
            "create",
            side_effect=lambda **kwargs: created_kwargs.update(kwargs) or config,
        ),
    ):
        command._run_via_service(username="business.profile", max_posts=1)

    assert created_kwargs["default_category"] is category


def test_cli_config_mode_passes_explicit_profile_url(monkeypatch):
    command = Command()
    config = SimpleNamespace(
        id=7,
        name="instagram",
        base_url="https://www.instagram.com",
        is_enabled=True,
    )
    captured = {}
    service = SimpleNamespace(
        run_scraper=lambda **kwargs: captured.update(kwargs) or SimpleNamespace()
    )
    monkeypatch.setattr(command, "_resolve_category", lambda slug: None)
    monkeypatch.setattr(command, "_print_session_stats", lambda value: None)
    monkeypatch.setattr(
        "apps.scrapers.services.ScraperIntegrationService",
        lambda: service,
    )

    with patch.object(ScraperConfig.objects, "get", return_value=config):
        command._run_with_config(
            7,
            1,
            "books",
            username="business.profile",
        )

    assert captured["start_url"] == "https://www.instagram.com/business.profile/"


def test_cli_config_mode_rejects_root_url_without_source(monkeypatch):
    command = Command()
    config = SimpleNamespace(
        id=7,
        name="instagram",
        base_url="https://www.instagram.com",
        is_enabled=True,
    )
    monkeypatch.setattr(command, "_resolve_category", lambda slug: None)

    with patch.object(ScraperConfig.objects, "get", return_value=config):
        with pytest.raises(CommandError, match="--username"):
            command._run_with_config(7, 1, "books")
