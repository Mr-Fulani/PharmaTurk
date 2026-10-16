"""Заявка «Найдём товар по ссылке или фото»: публичная форма без входа."""

from io import BytesIO
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from apps.orders.models import SourcingRequest
from apps.users.models import User

URL = "/api/orders/sourcing-requests/"


def _payload(**overrides):
    data = {
        "source_url": "https://www.trendyol.com/abc/product-p-123",
        "comment": "Нужен размер M",
        "quantity": 2,
        "contact_name": "Анна",
        "contact_phone": "+79990001122",
        "contact_channel": "telegram",
        "contact_username": "@anna_test",
    }
    data.update(overrides)
    return data


def _png_upload(name="photo.png"):
    buffer = BytesIO()
    Image.new("RGB", (40, 30), (200, 10, 10)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@pytest.fixture(autouse=True)
def _no_notifications():
    with patch("apps.orders.views.notify_sourcing_request_telegram.delay") as delay:
        yield delay


@pytest.mark.django_db(transaction=True)
def test_guest_can_submit_request_by_link(_no_notifications):
    response = APIClient().post(URL, _payload(), format="multipart")

    assert response.status_code == 201, response.data
    req = SourcingRequest.objects.get()
    assert req.user is None
    assert req.status == SourcingRequest.Status.NEW
    assert req.contact_username == "anna_test"
    assert req.quantity == 2
    _no_notifications.assert_called_once_with(req.pk)


@pytest.mark.django_db(transaction=True)
def test_photo_is_normalized_to_jpeg(settings, tmp_path):
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": str(tmp_path)}},
    }
    response = APIClient().post(URL, _payload(source_url="", image=_png_upload()), format="multipart")

    assert response.status_code == 201, response.data
    req = SourcingRequest.objects.get()
    assert req.image.name.endswith(".jpg")


@pytest.mark.django_db
def test_link_or_photo_is_required():
    response = APIClient().post(URL, _payload(source_url=""), format="multipart")

    assert response.status_code == 400
    assert SourcingRequest.objects.count() == 0


@pytest.mark.django_db
def test_only_http_links_are_accepted():
    response = APIClient().post(URL, _payload(source_url="javascript:alert(1)"), format="multipart")

    assert response.status_code == 400
    assert "source_url" in response.data


@pytest.mark.django_db
def test_email_channel_requires_email():
    response = APIClient().post(URL, _payload(contact_channel="email", contact_username=""), format="multipart")

    assert response.status_code == 400
    assert "contact_email" in response.data


@pytest.mark.django_db(transaction=True)
def test_honeypot_is_silently_ignored(_no_notifications):
    response = APIClient().post(URL, _payload(website="http://spam.example"), format="multipart")

    assert response.status_code == 201
    assert SourcingRequest.objects.count() == 0
    _no_notifications.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_logged_in_request_is_linked_to_user():
    user = User.objects.create_user(username="sourcing-user", email="s@example.test", password="x")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(URL, _payload(), format="multipart")

    assert response.status_code == 201, response.data
    assert SourcingRequest.objects.get().user == user


@pytest.mark.django_db
def test_telegram_notification_contains_contacts(settings):
    from types import SimpleNamespace

    from apps.orders.tasks import notify_sourcing_request_telegram

    settings.TELEGRAM_BOT_TOKEN = "token"
    settings.TELEGRAM_CHAT_ID = "admin-chat"
    req = SourcingRequest.objects.create(
        source_url="https://example.com/item_1",
        contact_name="Анна_*",
        contact_phone="+79990001122",
        contact_channel="whatsapp",
        contact_username="anna.wa",
    )
    with patch("apps.orders.tasks.requests.post", return_value=SimpleNamespace(ok=True, status_code=200)) as post:
        notify_sourcing_request_telegram.run(req.pk)

    text = post.call_args.kwargs["json"]["text"]
    assert "Новая заявка на поиск товара" in text
    assert "+79990001122" in text
    assert "WhatsApp: @anna.wa" in text
    assert "Анна\\_\\*" in text
    assert post.call_args.args[0].endswith("sendMessage")
