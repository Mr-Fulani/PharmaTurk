"""download_and_optimize_parsed_media: HTML-заглушка не сохраняется как картинка."""

from io import BytesIO

from PIL import Image

from apps.catalog.utils import parser_media_handler


class _FakeResponse:
    status_code = 200
    headers = {}


class _FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def head(self, url, headers=None):
        return _FakeResponse()


def _download(monkeypatch, content, saved):
    monkeypatch.setattr(parser_media_handler.httpx, "Client", _FakeClient)
    monkeypatch.setattr(parser_media_handler, "_get_media_bytes", lambda client, url, headers: (content, ""))
    monkeypatch.setattr(
        parser_media_handler.default_storage,
        "save",
        lambda path, file_obj: saved.append(path) or path,
    )
    monkeypatch.setattr(parser_media_handler.default_storage, "exists", lambda path: False)
    monkeypatch.setattr(parser_media_handler.default_storage, "url", lambda path: f"https://cdn.example/{path}")
    return parser_media_handler.download_and_optimize_parsed_media(
        "https://img-lcwaikiki.mncdn.com/pim/x_a.jpg", "lcw", "lcw-1", 0
    )


def test_html_stub_from_cdn_is_not_saved_as_image(monkeypatch):
    saved = []
    html = b"<!DOCTYPE html><html><head><title>Access Denied</title></head></html>"

    assert _download(monkeypatch, html, saved) == ""
    assert saved == []


def test_real_image_is_saved(monkeypatch):
    saved = []
    buffer = BytesIO()
    Image.new("RGB", (8, 8), "red").save(buffer, format="JPEG")

    url = _download(monkeypatch, buffer.getvalue(), saved)

    assert url.startswith("https://cdn.example/")
    assert len(saved) == 1
