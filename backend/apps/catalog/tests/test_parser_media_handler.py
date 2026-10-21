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


def _jpeg_bytes():
    buffer = BytesIO()
    Image.new("RGB", (8, 8), "blue").save(buffer, format="JPEG")
    return buffer.getvalue()


class _Response:
    def __init__(self, status_code, content=b"", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}


class _RecordingClient:
    """httpx.Client без сети: пишет заголовки каждого запроса."""

    def __init__(self, requests, *, head_type, get_status):
        self.requests = requests
        self.head_type = head_type
        self.get_status = get_status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def head(self, url, headers=None):
        self.requests.append(("HEAD", dict(headers or {})))
        return _Response(200, headers={"Content-Type": self.head_type} if self.head_type else {})

    def get(self, url, headers=None):
        headers = dict(headers or {})
        if "Range" in headers:
            self.requests.append(("RANGE", headers))
            return _Response(200, _jpeg_bytes())
        self.requests.append(("GET", headers))
        if self.get_status >= 400:
            return _Response(self.get_status)
        return _Response(self.get_status, _jpeg_bytes(), {"Content-Type": "image/jpeg"})


def record_media_requests(monkeypatch, *, head_type="image/jpeg", get_status=200):
    """Подменяет сеть и storage загрузчика; возвращает список (метод, заголовки)."""
    requests = []
    monkeypatch.setattr(
        parser_media_handler.httpx,
        "Client",
        lambda *a, **k: _RecordingClient(requests, head_type=head_type, get_status=get_status),
    )
    monkeypatch.setattr(parser_media_handler.default_storage, "save", lambda path, file_obj: path)
    monkeypatch.setattr(parser_media_handler.default_storage, "exists", lambda path: False)
    monkeypatch.setattr(parser_media_handler.default_storage, "url", lambda path: f"https://cdn.example/{path}")
    return requests


def _download_recorded(monkeypatch, headers=None, **client_options):
    requests = record_media_requests(monkeypatch, **client_options)
    url = parser_media_handler.download_and_optimize_parsed_media(
        "https://img-lcwaikiki.mncdn.com/pim/x_a.jpg", "lcw", "lcw-1", 0, headers=headers
    )
    assert url.startswith("https://cdn.example/")
    return [(method, sent.get("User-Agent")) for method, sent in requests], requests


def _browser_user_agent(value):
    return bool(value) and value.startswith("Mozilla/5.0 (Windows") and "Chrome/" in value


def test_head_and_get_send_browser_user_agent_by_default(monkeypatch):
    # mncdn (LC Waikiki, FLO) отвечает 422 без браузерного User-Agent.
    user_agents, _ = _download_recorded(monkeypatch)

    assert [method for method, _ in user_agents] == ["HEAD", "GET"]
    assert all(_browser_user_agent(ua) for _, ua in user_agents)


def test_range_fallback_sends_browser_user_agent(monkeypatch):
    user_agents, _ = _download_recorded(monkeypatch, head_type="", get_status=403)

    assert [method for method, _ in user_agents] == ["HEAD", "GET", "RANGE"]
    assert all(_browser_user_agent(ua) for _, ua in user_agents)


def test_configured_user_agent_is_kept(monkeypatch):
    _, requests = _download_recorded(
        monkeypatch, headers={"user-agent": "Custom/1.0", "Referer": "https://x.example"}
    )

    assert [sent.get("user-agent") for _, sent in requests] == ["Custom/1.0", "Custom/1.0"]
    assert all("User-Agent" not in sent for _, sent in requests)
    assert all(sent["Referer"] == "https://x.example" for _, sent in requests)
