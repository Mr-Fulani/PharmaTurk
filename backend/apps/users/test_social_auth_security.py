import logging
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings
from PIL import Image

from apps.users import social_auth


class _Response:
    def __init__(self, *, status_code=200, payload=None, headers=None, chunks=()):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self._chunks = chunks

    def json(self):
        return self._payload

    def iter_bytes(self):
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class _QueryResult:
    def __init__(self, *, first=None, exists=False):
        self._first = first
        self._exists = exists

    def first(self):
        return self._first

    def exists(self):
        return self._exists

    def exclude(self, **criteria):
        return self


def _mock_http_client(response):
    client = MagicMock()
    client.__enter__.return_value = client
    client.get.return_value = response
    client.stream.return_value = response
    return client


def _png_bytes(size=(2, 2)):
    output = BytesIO()
    Image.new("RGB", size, color=(30, 60, 90)).save(output, format="PNG")
    return output.getvalue()


def _google_claims(**overrides):
    claims = {
        "aud": "expected-client-id",
        "iss": "https://accounts.google.com",
        "sub": "google-user-1",
        "email": "person@example.com",
        # Google tokeninfo currently serialises this claim as a string.
        "email_verified": "true",
    }
    claims.update(overrides)
    return claims


@override_settings(GOOGLE_CLIENT_ID="")
def test_google_fails_closed_without_client_id():
    with patch.object(social_auth.httpx, "Client") as client_factory:
        assert social_auth.GoogleOAuthProvider().get_user_info("a.b.c") is None

    client_factory.assert_not_called()


@override_settings(GOOGLE_CLIENT_ID="expected-client-id")
def test_google_rejects_opaque_access_token_without_userinfo_fallback():
    with patch.object(social_auth.httpx, "Client") as client_factory:
        assert social_auth.GoogleOAuthProvider().get_user_info("opaque-access-token") is None

    client_factory.assert_not_called()


@override_settings(GOOGLE_CLIENT_ID="expected-client-id")
def test_google_requires_exact_audience():
    response = _Response(payload=_google_claims(aud="expected-client-id-extra"))
    client = _mock_http_client(response)

    with patch.object(social_auth.httpx, "Client", return_value=client):
        assert social_auth.GoogleOAuthProvider().get_user_info("a.b.c") is None


@pytest.mark.parametrize("claim", [False, "false", None])
@override_settings(GOOGLE_CLIENT_ID="expected-client-id")
def test_google_rejects_email_without_verified_assertion(claim):
    response = _Response(payload=_google_claims(email_verified=claim))
    client = _mock_http_client(response)

    with patch.object(social_auth.httpx, "Client", return_value=client):
        assert social_auth.GoogleOAuthProvider().get_user_info("a.b.c") is None


@override_settings(GOOGLE_CLIENT_ID="expected-client-id")
def test_google_normalises_verified_email_claim():
    response = _Response(payload=_google_claims(email="  person@example.com  "))
    client = _mock_http_client(response)

    with patch.object(social_auth.httpx, "Client", return_value=client) as client_factory:
        result = social_auth.GoogleOAuthProvider().get_user_info("a.b.c")

    assert result == {
        "provider_id": "google-user-1",
        "email": "person@example.com",
        "email_verified": True,
        "first_name": "",
        "last_name": "",
        "avatar_url": None,
    }
    assert client_factory.call_args.kwargs["follow_redirects"] is False


@override_settings(GOOGLE_CLIENT_ID="expected-client-id")
def test_google_network_error_does_not_log_id_token(caplog):
    token = "header.secret-payload.signature"
    client = MagicMock()
    client.__enter__.return_value = client
    client.get.side_effect = RuntimeError(f"request failed for ?id_token={token}")
    caplog.set_level(logging.DEBUG, logger=social_auth.__name__)

    with patch.object(social_auth.httpx, "Client", return_value=client):
        assert social_auth.GoogleOAuthProvider().get_user_info(token) is None

    assert token not in caplog.text


@override_settings(VK_APP_ID="vk-app", VK_USER_TOKEN="service-token", VK_API_TOKEN="")
def test_vk_enrichment_uses_open_client_and_marks_oidc_email_verified():
    class ActiveClient:
        def __init__(self):
            self.active = False
            self.enrichment_called = False

        def __enter__(self):
            self.active = True
            return self

        def __exit__(self, exc_type, exc, traceback):
            self.active = False
            return False

        def post(self, url, data):
            assert self.active
            return _Response(
                payload={
                    "user": {
                        "user_id": 123,
                        "email": "vk@example.com",
                        "first_name": "OIDC",
                        "last_name": "User",
                        "avatar": "https://sun9-1.userapi.com/avatar.jpg",
                    }
                }
            )

        def get(self, url, params):
            assert self.active
            self.enrichment_called = True
            return _Response(
                payload={
                    "response": [
                        {
                            "first_name": "Enriched",
                            "last_name": "User",
                            "photo_100": "https://sun9-2.userapi.com/avatar.jpg",
                        }
                    ]
                }
            )

    client = ActiveClient()
    with patch.object(social_auth.httpx, "Client", return_value=client):
        result = social_auth.VKOAuthProvider().get_user_info("vk-token", vk_user_id="123")

    assert client.enrichment_called is True
    assert client.active is False
    assert result == {
        "provider_id": "123",
        "email": "vk@example.com",
        "email_verified": True,
        "first_name": "Enriched",
        "last_name": "User",
        "avatar_url": "https://sun9-2.userapi.com/avatar.jpg",
    }


@override_settings(VK_APP_ID="", VK_USER_TOKEN="", VK_API_TOKEN="")
def test_vk_classic_api_never_selects_user_from_client_supplied_id():
    response = _Response(
        payload={
            "response": [
                {
                    "id": 123,
                    "first_name": "Token",
                    "last_name": "Owner",
                    "photo_100": "https://sun9-2.userapi.com/avatar.jpg",
                }
            ]
        }
    )
    client = _mock_http_client(response)

    with patch.object(social_auth.httpx, "Client", return_value=client):
        result = social_auth.VKOAuthProvider().get_user_info("vk-token", vk_user_id="999")

    assert result is None
    assert "user_ids" not in client.get.call_args.kwargs["params"]


@override_settings(VK_APP_ID="", VK_USER_TOKEN="", VK_API_TOKEN="")
def test_vk_network_error_does_not_log_access_token(caplog):
    token = "vk-sensitive-access-token"
    client = MagicMock()
    client.__enter__.return_value = client
    client.get.side_effect = RuntimeError(f"request failed for ?access_token={token}")
    caplog.set_level(logging.WARNING, logger=social_auth.__name__)

    with patch.object(social_auth.httpx, "Client", return_value=client):
        assert social_auth.VKOAuthProvider().get_user_info(token) is None

    assert token not in caplog.text


@pytest.mark.parametrize(
    ("provider", "url", "allowed"),
    [
        ("google", "https://lh3.googleusercontent.com/a/photo", True),
        ("google", "http://lh3.googleusercontent.com/a/photo", False),
        ("google", "https://lh4.googleusercontent.com/a/photo", False),
        ("google", "https://lh3.googleusercontent.com.evil.example/a/photo", False),
        ("google", "https://user@lh3.googleusercontent.com/a/photo", False),
        ("google", "https://lh3.googleusercontent.com:444/a/photo", False),
        ("vk", "https://sun9-77.userapi.com/avatar", True),
        ("vk", "https://eviluserapi.com/avatar", False),
        ("vk", "https://vk.com/avatar", False),
        ("unknown", "https://lh3.googleusercontent.com/a/photo", False),
    ],
)
def test_avatar_url_provider_allowlists(provider, url, allowed):
    assert social_auth._is_allowed_avatar_url(provider, url) is allowed


def test_avatar_download_disables_redirects_and_accepts_valid_image():
    content = _png_bytes()
    response = _Response(
        headers={"content-type": "image/png", "content-length": str(len(content))},
        chunks=(content,),
    )
    client = _mock_http_client(response)

    with patch.object(social_auth.httpx, "Client", return_value=client) as client_factory:
        result = social_auth._download_social_avatar(
            "google", "https://lh3.googleusercontent.com/a/photo"
        )

    assert result == ("png", content)
    assert client_factory.call_args.kwargs["follow_redirects"] is False


def test_avatar_download_does_not_follow_redirect_response():
    response = _Response(status_code=302, headers={"location": "https://example.com/private"})
    client = _mock_http_client(response)

    with patch.object(social_auth.httpx, "Client", return_value=client):
        assert (
            social_auth._download_social_avatar(
                "google", "https://lh3.googleusercontent.com/a/photo"
            )
            is None
        )


def test_avatar_download_stops_above_two_megabytes():
    oversized_chunk = b"x" * (social_auth.MAX_AVATAR_BYTES + 1)
    response = _Response(
        headers={"content-type": "image/png"},
        chunks=(oversized_chunk,),
    )
    client = _mock_http_client(response)

    with patch.object(social_auth.httpx, "Client", return_value=client):
        assert (
            social_auth._download_social_avatar(
                "google", "https://lh3.googleusercontent.com/a/photo"
            )
            is None
        )


def test_avatar_rejects_mime_spoof_and_excessive_dimensions():
    png = _png_bytes()
    assert social_auth._validated_avatar_extension(png, "image/jpeg") is None
    assert social_auth._validated_avatar_extension(b"not-an-image", "image/png") is None

    oversized_dimensions = _png_bytes(size=(4001, 4000))
    assert len(oversized_dimensions) < social_auth.MAX_AVATAR_BYTES
    assert social_auth._validated_avatar_extension(oversized_dimensions, "image/png") is None


def test_factory_does_not_link_or_store_unverified_email():
    manager = MagicMock()
    created_user = SimpleNamespace(id=10, avatar=None, save=MagicMock())
    manager.create_user.return_value = created_user
    manager.filter.return_value = _QueryResult()
    provider = SimpleNamespace(name="google", id_field="google_id")

    with patch.object(social_auth.User, "objects", manager):
        result = social_auth.get_or_create_social_user(
            provider,
            {
                "provider_id": "attacker-provider-id",
                "email": "victim@example.com",
                "email_verified": False,
                "first_name": "",
                "last_name": "",
                "avatar_url": None,
            },
        )

    assert result is created_user
    assert not any(
        call.kwargs == {"email": "victim@example.com"}
        for call in manager.filter.call_args_list
    )
    create_kwargs = manager.create_user.call_args.kwargs
    assert create_kwargs["email"] == "google_attacker-provider-id@mudaroba.local"
    assert create_kwargs["is_verified"] is False


def test_factory_links_existing_email_only_with_explicit_true_assertion():
    manager = MagicMock()
    existing_user = SimpleNamespace(
        id=11,
        avatar=None,
        first_name="Existing",
        last_name="User",
        email="person@example.com",
        is_verified=False,
        google_id=None,
        save=MagicMock(),
    )

    def filter_users(**criteria):
        if criteria == {"email__iexact": "person@example.com"}:
            return _QueryResult(first=existing_user)
        return _QueryResult()

    manager.filter.side_effect = filter_users
    provider = SimpleNamespace(name="google", id_field="google_id")

    with patch.object(social_auth.User, "objects", manager):
        result = social_auth.get_or_create_social_user(
            provider,
            {
                "provider_id": "verified-provider-id",
                "email": "person@example.com",
                "email_verified": True,
                "first_name": "",
                "last_name": "",
                "avatar_url": None,
            },
        )

    assert result is existing_user
    assert existing_user.google_id == "verified-provider-id"
    assert existing_user.is_verified is True
    existing_user.save.assert_called_once_with(update_fields=["google_id", "is_verified"])


def test_factory_promotes_provider_account_after_verified_email_arrives():
    manager = MagicMock()
    existing_user = SimpleNamespace(
        id=14,
        pk=14,
        avatar=None,
        first_name="Existing",
        last_name="User",
        email="google_provider-id@mudaroba.local",
        is_verified=False,
        save=MagicMock(),
    )

    def filter_users(**criteria):
        if criteria == {"google_id": "provider-id"}:
            return _QueryResult(first=existing_user)
        if criteria == {"email__iexact": "verified@example.com"}:
            return _QueryResult(exists=False)
        return _QueryResult()

    manager.filter.side_effect = filter_users
    provider = SimpleNamespace(name="google", id_field="google_id")

    with patch.object(social_auth.User, "objects", manager):
        result = social_auth.get_or_create_social_user(
            provider,
            {
                "provider_id": "provider-id",
                "email": "verified@example.com",
                "email_verified": True,
                "first_name": "",
                "last_name": "",
                "avatar_url": None,
            },
        )

    assert result is existing_user
    assert existing_user.email == "verified@example.com"
    assert existing_user.is_verified is True
    existing_user.save.assert_called_once_with(update_fields=["email", "is_verified"])


def test_factory_marks_new_user_verified_only_for_verified_email_assertion():
    manager = MagicMock()
    created_user = SimpleNamespace(id=12, avatar=None, save=MagicMock())
    manager.create_user.return_value = created_user
    manager.filter.return_value = _QueryResult()
    provider = SimpleNamespace(name="google", id_field="google_id")

    with patch.object(social_auth.User, "objects", manager):
        social_auth.get_or_create_social_user(
            provider,
            {
                "provider_id": "new-provider-id",
                "email": "new@example.com",
                "email_verified": True,
                "first_name": "New",
                "last_name": "User",
                "avatar_url": None,
            },
        )

    create_kwargs = manager.create_user.call_args.kwargs
    assert create_kwargs["email"] == "new@example.com"
    assert create_kwargs["is_verified"] is True


def test_factory_gracefully_skips_avatar_storage_failure():
    class FailingAvatar:
        def __bool__(self):
            return False

        def save(self, *args, **kwargs):
            raise OSError("storage unavailable")

    manager = MagicMock()
    existing_user = SimpleNamespace(
        id=13,
        avatar=FailingAvatar(),
        first_name="Existing",
        last_name="User",
        save=MagicMock(),
    )
    manager.filter.return_value = _QueryResult(first=existing_user)
    provider = SimpleNamespace(name="google", id_field="google_id")

    with (
        patch.object(social_auth.User, "objects", manager),
        patch.object(social_auth, "_download_social_avatar", return_value=("png", b"image")),
    ):
        result = social_auth.get_or_create_social_user(
            provider,
            {
                "provider_id": "existing-provider-id",
                "email": "person@example.com",
                "email_verified": True,
                "first_name": "",
                "last_name": "",
                "avatar_url": "https://lh3.googleusercontent.com/a/photo",
            },
        )

    assert result is existing_user
    existing_user.save.assert_not_called()
