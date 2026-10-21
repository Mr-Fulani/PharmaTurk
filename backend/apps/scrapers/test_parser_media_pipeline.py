"""Скачивание медиа парсеров: User-Agent, галереи цветов, повторный проход."""

from io import BytesIO
from types import SimpleNamespace

from PIL import Image

from apps.catalog.utils import parser_media_handler
from apps.scrapers.services import ScraperIntegrationService

LCW_IMAGE = "https://img-lcwaikiki.mncdn.com/mnresize/1020/1360/pim/productimages/1/a.jpg"


def _session(*, user_agent="", max_images=5):
    config = SimpleNamespace(
        user_agent=user_agent,
        headers={},
        max_images_per_product=max_images,
        parser_class="lcw",
    )
    return SimpleNamespace(scraper_config=config, max_images_per_product=None)


def _jpeg_bytes():
    buffer = BytesIO()
    Image.new("RGB", (8, 8), "green").save(buffer, format="JPEG")
    return buffer.getvalue()


class _Response:
    def __init__(self, status_code, content=b"", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}


def _record_user_agents(monkeypatch):
    """Сеть загрузчика без HTTP: CDN, как mncdn, отвечает 422 без User-Agent."""
    sent = []

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def _respond(self, method, headers):
            ua = (headers or {}).get("User-Agent", "")
            sent.append((method, ua))
            if not ua:
                return _Response(422)
            return _Response(200, _jpeg_bytes(), {"Content-Type": "image/jpeg"})

        def head(self, url, headers=None):
            return self._respond("HEAD", headers)

        def get(self, url, headers=None):
            return self._respond("GET", headers)

    monkeypatch.setattr(parser_media_handler.httpx, "Client", Client)
    monkeypatch.setattr(parser_media_handler.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(parser_media_handler.default_storage, "save", lambda path, file_obj: path)
    monkeypatch.setattr(parser_media_handler.default_storage, "exists", lambda path: False)
    monkeypatch.setattr(parser_media_handler.default_storage, "url", lambda path: f"https://cdn.example/{path}")
    return sent


def test_media_download_without_configured_user_agent_uses_browser_one(monkeypatch):
    sent = _record_user_agents(monkeypatch)

    images, _ = ScraperIntegrationService()._download_parsed_media_urls(
        _session(user_agent=""),
        source_urls=[LCW_IMAGE],
        parser_name="lcw",
        product_id="lcw-1",
        sub_folder=None,
    )

    assert len(images) == 1 and "/products/parsed/lcw/" in images[0]
    assert [method for method, _ in sent] == ["HEAD", "GET"]
    assert all(ua.startswith("Mozilla/5.0 (Windows") and "Chrome/" in ua for _, ua in sent)


def test_media_download_keeps_configured_user_agent(monkeypatch):
    sent = _record_user_agents(monkeypatch)

    images, _ = ScraperIntegrationService()._download_parsed_media_urls(
        _session(user_agent="Configured/2.0"),
        source_urls=[LCW_IMAGE],
        parser_name="lcw",
        product_id="lcw-1",
        sub_folder=None,
    )

    assert len(images) == 1
    assert sent == [("HEAD", "Configured/2.0"), ("GET", "Configured/2.0")]
