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
from apps.scrapers.parsers.instagram import (
    InstagramParser,
    InstagramRateLimitedError,
    InstagramSourceError,
)


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


def test_post_without_caption_price_remains_available(monkeypatch):
    parser = InstagramParser()
    monkeypatch.setattr(
        parser,
        "_extract_all_media",
        lambda _post: (["https://cdn.example/POST1.jpg"], []),
    )
    post = SimpleNamespace(
        caption="Новая модель буркини. За подробностями пишите менеджеру.",
        shortcode="POST1",
        date_utc=None,
        owner_username="manual.shop",
        is_video=False,
        likes=10,
        comments=2,
    )

    product = parser._parse_post(post)

    assert product.price is None
    assert product.is_available is True
    assert product.stock_quantity is None


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


def test_profile_task_callbacks_publish_each_post_without_accumulating(monkeypatch):
    parser = InstagramParser(max_retries=1)
    _patch_product_conversion(monkeypatch, parser)
    monkeypatch.setattr(
        instaloader.Profile,
        "from_username",
        lambda *args, **kwargs: SimpleNamespace(
            get_posts=lambda: iter([_post("POST1"), _post("POST2")])
        ),
    )
    controls = []
    saved = []
    progress = []
    parser.configure_task_callbacks(
        control_callback=lambda: controls.append("checked"),
        product_callback=lambda product: saved.append(product.external_id) or True,
        progress_callback=lambda *args: progress.append(args),
    )

    products = parser.parse_product_list(
        "https://www.instagram.com/business.profile/",
        max_pages=2,
    )

    assert products == []
    assert saved == ["POST1", "POST2"]
    assert len(controls) == 2
    assert [item[0] for item in progress] == [1, 2]
    assert [item[2] for item in progress] == ["POST1", "POST2"]


def test_profile_task_callback_can_stop_after_safely_publishing_current_post(monkeypatch):
    parser = InstagramParser(max_retries=1)
    _patch_product_conversion(monkeypatch, parser)
    monkeypatch.setattr(
        instaloader.Profile,
        "from_username",
        lambda *args, **kwargs: SimpleNamespace(
            get_posts=lambda: iter([_post("POST1"), _post("POST2")])
        ),
    )
    saved = []
    progress = []
    parser.configure_task_callbacks(
        product_callback=lambda product: saved.append(product.external_id) or False,
        progress_callback=lambda *args: progress.append(args),
    )

    parser.parse_product_list(
        "https://www.instagram.com/business.profile/",
        max_pages=2,
    )

    assert saved == ["POST1"]
    assert len(progress) == 1
    assert progress[0][2] == "POST1"


def test_profile_task_control_exception_is_not_swallowed(monkeypatch):
    parser = InstagramParser(max_retries=1)
    monkeypatch.setattr(
        instaloader.Profile,
        "from_username",
        lambda *args, **kwargs: SimpleNamespace(get_posts=lambda: iter([_post("POST1")])),
    )
    parser.configure_task_callbacks(
        control_callback=lambda: (_ for _ in ()).throw(RuntimeError("paused")),
    )

    with pytest.raises(RuntimeError, match="paused"):
        parser.parse_product_list(
            "https://www.instagram.com/business.profile/",
            max_pages=1,
        )


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
    config = SimpleNamespace(scraper_username="")
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


def test_parser_has_no_password_login(monkeypatch):
    # TD-016: пароль не хранится и не используется — без sessionid работаем анонимно.
    parser = InstagramParser(username="bot")
    monkeypatch.setattr(
        parser.loader,
        "login",
        lambda *args, **kwargs: pytest.fail("password login must never run"),
    )

    parser._ensure_authenticated()

    assert not parser.password
    assert parser._authenticated is False
    assert not parser.loader.context.is_logged_in


def test_configured_sessionid_cookie_logs_in_and_keeps_proxy(monkeypatch):
    monkeypatch.setattr(settings, "SCRAPER_PROXY_URL", "http://proxy.example:8080")
    parser = InstagramParser(username="bot", use_proxy=True)
    monkeypatch.setattr(
        parser.loader,
        "login",
        lambda *args, **kwargs: pytest.fail("password login must never run"),
    )
    parser.configure_request_identity(cookies={"sessionid": "browser-session", "csrftoken": "t"})

    session = parser.loader.context._session
    assert parser._authenticated is True
    assert parser.loader.context.is_logged_in
    assert parser.loader.context.username == "bot"
    assert session.cookies.get("sessionid") == "browser-session"
    assert session.headers["X-CSRFToken"] == "t"
    # Instaloader.load_session заменил бы requests.Session и потерял прокси.
    assert session.proxies["https"] == "http://proxy.example:8080"


def test_rate_controller_raises_on_429_instead_of_sleeping(monkeypatch):
    parser = InstagramParser()
    monkeypatch.setattr(
        "time.sleep",
        lambda *args: pytest.fail("worker must not sleep on HTTP 429"),
    )
    controller = parser.loader.context._rate_controller

    with pytest.raises(InstagramRateLimitedError, match="429"):
        controller.handle_429("other")


def test_rate_controller_raises_instead_of_long_proactive_wait(monkeypatch):
    parser = InstagramParser()
    controller = parser.loader.context._rate_controller
    monkeypatch.setattr(controller, "query_waittime", lambda *args: 600.0)
    monkeypatch.setattr(
        controller,
        "sleep",
        lambda secs: pytest.fail("worker must not sleep for minutes"),
    )

    with pytest.raises(InstagramRateLimitedError, match="10 мин"):
        controller.wait_before_query("other")


def test_rate_controller_keeps_short_waits(monkeypatch):
    parser = InstagramParser()
    controller = parser.loader.context._rate_controller
    slept = []
    monkeypatch.setattr(controller, "query_waittime", lambda *args: 3.0)
    monkeypatch.setattr(controller, "sleep", slept.append)

    controller.wait_before_query("other")

    assert slept == [3.0]


def test_profile_429_does_not_hammer_mobile_feed_fallback(monkeypatch):
    parser = InstagramParser()

    def rate_limited(*args, **kwargs):
        raise InstagramRateLimitedError()

    monkeypatch.setattr(instaloader.Profile, "from_username", rate_limited)
    monkeypatch.setattr(
        parser,
        "_iter_mobile_feed_posts",
        lambda *args, **kwargs: pytest.fail("fallback must not run after 429"),
    )

    with pytest.raises(InstagramRateLimitedError):
        parser.parse_product_list("https://www.instagram.com/business.profile/")


def test_connection_error_with_429_becomes_rate_limit(monkeypatch):
    # При max_connection_attempts=1 Instaloader не зовёт handle_429, а отдаёт
    # ConnectionException с текстом ответа.
    parser = InstagramParser()
    monkeypatch.setattr(
        instaloader.Post,
        "from_shortcode",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            instaloader.exceptions.ConnectionException(
                "JSON Query to graphql/query: 429 Too Many Requests"
            )
        ),
    )

    with pytest.raises(InstagramRateLimitedError):
        parser.parse_product_detail("https://www.instagram.com/p/POST1/")


def test_mobile_feed_429_becomes_rate_limit(monkeypatch):
    parser = InstagramParser()
    monkeypatch.setattr(
        parser.loader.context._session,
        "get",
        lambda *args, **kwargs: _FeedResponse({}, status_code=429),
    )

    with pytest.raises(InstagramRateLimitedError):
        list(parser._iter_mobile_feed_posts("business.profile", max_posts=1))


@pytest.mark.django_db
def test_scraper_config_has_no_password_field():
    field_names = {field.name for field in ScraperConfig._meta.get_fields()}

    assert "scraper_password" not in field_names
    assert "scraper_username" in field_names
