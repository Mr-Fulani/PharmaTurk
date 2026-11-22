"""Чек и фото клиента в админке отдаются по правам, а не публичной ссылкой CDN."""

import io
from unittest.mock import MagicMock, patch

import pytest
from django.contrib import admin
from django.core.files.base import ContentFile
from django.test import Client
from django.urls import reverse

from apps.orders.admin import OrderAdmin, SourcingRequestAdmin
from apps.orders.models import Order, SourcingRequest
from apps.orders.sourcing import create_order_for_sourcing_request
from apps.users.models import User


@pytest.fixture(autouse=True)
def plain_staticfiles(settings):
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


def _user(username, **flags):
    return User.objects.create_user(
        username=username, email=f"{username}@example.test", password="test-only-password", **flags
    )


def _client(user):
    client = Client()
    client.force_login(user)
    return client


def _request_with_photo():
    req = SourcingRequest.objects.create(
        comment="Кроссовки 42", quantity=1, contact_name="Анна",
        contact_phone="+79990001122", contact_channel="whatsapp",
    )
    req.image.save("client.jpg", ContentFile(b"\xff\xd8\xff\xe0 client photo"), save=True)
    return req, create_order_for_sourcing_request(req)


@pytest.mark.django_db
def test_admin_markup_links_to_admin_views_not_to_storage():
    req, order = _request_with_photo()
    Order.objects.filter(pk=order.pk).update(receipt_url="https://cdn.example.test/receipts/x/1.pdf")
    order.refresh_from_db()

    photo_url = reverse("admin:orders_sourcingrequest_photo", args=[req.pk])
    receipt_url = reverse("admin:orders_order_receipt_pdf", args=[order.pk])
    order_admin = OrderAdmin(Order, admin.site)
    request_admin = SourcingRequestAdmin(SourcingRequest, admin.site)

    assert photo_url in str(order_admin.sourcing_details(order))
    assert photo_url in str(request_admin.image_preview(req))
    assert receipt_url in str(order_admin.receipt_link(order))
    for markup in (
        order_admin.sourcing_details(order),
        request_admin.image_preview(req),
        order_admin.receipt_link(order),
    ):
        assert req.image.url not in str(markup)
        assert "cdn.example.test" not in str(markup)


@pytest.mark.django_db
def test_photo_is_served_to_staff_with_rights_only():
    req, _order = _request_with_photo()
    url = reverse("admin:orders_sourcingrequest_photo", args=[req.pk])

    allowed = _client(_user("photo-admin", is_staff=True, is_superuser=True)).get(url)
    assert allowed.status_code == 200
    assert allowed["Content-Type"] == "image/jpeg"
    assert b"client photo" in b"".join(allowed.streaming_content)
    assert "no-store" in allowed["Cache-Control"]

    assert _client(_user("photo-staff-no-rights", is_staff=True)).get(url).status_code == 403
    assert _client(_user("photo-customer")).get(url).status_code == 302
    assert Client().get(url).status_code == 302


@pytest.mark.django_db
def test_receipt_is_served_to_staff_with_rights_only():
    _req, order = _request_with_photo()
    Order.objects.filter(pk=order.pk).update(receipt_url="https://cdn.example.test/receipts/x/1.pdf")
    url = reverse("admin:orders_order_receipt_pdf", args=[order.pk])
    storage_client = MagicMock()
    storage_client.get_object.return_value = {"Body": io.BytesIO(b"%PDF-1.7 receipt")}

    with patch("apps.catalog.utils.r2_utils.get_r2_client", return_value=storage_client):
        allowed = _client(_user("receipt-admin", is_staff=True, is_superuser=True)).get(url)
        denied = _client(_user("receipt-staff-no-rights", is_staff=True)).get(url)
        anonymous = Client().get(url)

    assert allowed.status_code == 200
    assert allowed["Content-Type"] == "application/pdf"
    assert allowed.content == b"%PDF-1.7 receipt"
    assert "no-store" in allowed["Cache-Control"]
    assert denied.status_code == 403
    assert anonymous.status_code == 302
    assert storage_client.get_object.call_count == 1


@pytest.mark.django_db
def test_order_without_receipt_gives_404():
    _req, order = _request_with_photo()
    url = reverse("admin:orders_order_receipt_pdf", args=[order.pk])

    response = _client(_user("receipt-admin-2", is_staff=True, is_superuser=True)).get(url)

    assert response.status_code == 404
