from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.feedback.models import ProductReview
from apps.users.models import User
from apps.feedback.tasks import notify_admin_product_review


@pytest.fixture
def review_user(db):
    return User.objects.create_user(
        email="reviewer@example.com",
        username="reviewer",
        password="password",
        first_name="Review",
        last_name="Author",
    )


@pytest.fixture
def resolved_product():
    with patch(
        "apps.catalog.services.product_resolve.resolve_product_payload",
        return_value=({"slug": "test-product", "name": "Test Product"}, "generic_product", "medicines"),
    ):
        yield


def review_payload():
    return {
        "product_type": "medicines",
        "product_slug": "test-product",
        "product_name": "Ignored client title",
        "rating": 5,
        "text": "A useful and detailed review.",
    }


@pytest.mark.django_db
def test_product_review_requires_authentication(resolved_product):
    response = APIClient().post("/api/feedback/product-reviews/", review_payload(), format="json")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_review_is_pending_hidden_and_unique(review_user, resolved_product):
    client = APIClient()
    client.force_authenticate(review_user)

    with patch("apps.feedback.views.notify_admin_product_review.delay") as notify:
        created = client.post("/api/feedback/product-reviews/", review_payload(), format="json")

    assert created.status_code == status.HTTP_201_CREATED
    assert created.data["status"] == ProductReview.Status.PENDING
    assert created.data["author_name"] == "Review Author"
    assert created.data["product_name"] == "Test Product"
    notify.assert_called_once_with(created.data["id"], "created")

    duplicate = client.post("/api/feedback/product-reviews/", review_payload(), format="json")
    assert duplicate.status_code == status.HTTP_409_CONFLICT

    public = APIClient().get(
        "/api/feedback/product-reviews/",
        {"product_type": "medicines", "product_slug": "test-product"},
    )
    assert public.status_code == status.HTTP_200_OK
    assert public.data["reviews_count"] == 0
    assert public.data["reviews"] == []


@pytest.mark.django_db
def test_approved_review_is_aggregated_and_edit_returns_to_moderation(review_user, resolved_product):
    review = ProductReview.objects.create(
        user=review_user,
        product_type="medicines",
        product_slug="test-product",
        product_name="Test Product",
        author_name="Review Author",
        rating=4,
        text="Original review",
        status=ProductReview.Status.APPROVED,
    )
    public = APIClient().get(
        "/api/feedback/product-reviews/",
        {"product_type": "medicines", "product_slug": "test-product"},
    )
    assert public.data["reviews_count"] == 1
    assert public.data["average_rating"] == 4.0

    client = APIClient()
    client.force_authenticate(review_user)
    with patch("apps.feedback.views.notify_admin_product_review.delay"):
        updated = client.patch(
            f"/api/feedback/product-reviews/{review.pk}/",
            {"rating": 2, "text": "Updated review"},
            format="json",
        )
    assert updated.status_code == status.HTTP_200_OK
    review.refresh_from_db()
    assert review.status == ProductReview.Status.PENDING
    assert review.published_at is None


@pytest.mark.django_db
def test_review_rejects_more_than_three_media(review_user, resolved_product):
    client = APIClient()
    client.force_authenticate(review_user)
    payload = review_payload()
    payload["media"] = [
        SimpleUploadedFile(f"photo-{index}.jpg", b"content", content_type="image/jpeg")
        for index in range(4)
    ]
    response = client.post("/api/feedback/product-reviews/", payload, format="multipart")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert not ProductReview.objects.exists()


@pytest.mark.django_db
@override_settings(TELEGRAM_BOT_TOKEN="bot-token", TELEGRAM_CHAT_ID="123", SITE_URL="https://example.com")
def test_product_review_sends_admin_telegram_notification(review_user):
    review = ProductReview.objects.create(
        user=review_user,
        product_type="medicines",
        product_slug="test-product",
        product_name="Test Product",
        author_name="Review Author",
        rating=5,
        text="Notification review",
    )
    with patch("apps.feedback.tasks.requests.post") as post:
        post.return_value.raise_for_status.return_value = None
        notify_admin_product_review.run(review.pk, "created")

    payload = post.call_args.kwargs["json"]
    assert payload["chat_id"] == "123"
    assert "Новый отзыв" in payload["text"]
    assert f"/admin/feedback/productreview/{review.pk}/change/" in payload["text"]
