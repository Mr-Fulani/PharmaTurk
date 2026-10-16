"""Ответ магазина на отзыв о товаре."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.admin.sites import AdminSite

from apps.feedback.admin import ProductReviewAdmin
from apps.feedback.models import ProductReview
from apps.feedback.serializers import ProductReviewSerializer
from apps.users.models import User


@pytest.fixture
def review(db):
    author = User.objects.create_user(
        email="author@example.com", username="review-author", password="x",
        telegram_id="999", telegram_notifications=True,
    )
    return ProductReview.objects.create(
        user=author,
        product_type="medicines",
        product_slug="reply-product",
        product_name="Reply Product",
        author_name="Автор",
        rating=4,
        text="Хороший товар",
        status=ProductReview.Status.APPROVED,
    )


@pytest.fixture
def staff(db):
    return User.objects.create_user(
        email="staff@example.com", username="reply-staff", password="x", is_staff=True, is_superuser=True,
    )


def _save_reply(review, staff, rf, reply):
    review.admin_reply = reply
    request = rf.post("/admin/")
    request.user = staff
    form = SimpleNamespace(changed_data=["admin_reply"])
    with patch("apps.feedback.admin.notify_review_author_reply.delay") as delay, \
            patch("apps.feedback.admin.transaction.on_commit", side_effect=lambda fn: fn()):
        ProductReviewAdmin(ProductReview, AdminSite()).save_model(request, review, form, change=True)
    return delay


@pytest.mark.django_db
def test_admin_reply_sets_author_and_time_and_notifies(review, staff, rf):
    delay = _save_reply(review, staff, rf, "  Спасибо за отзыв!  ")

    review.refresh_from_db()
    assert review.admin_reply == "Спасибо за отзыв!"
    assert review.admin_replied_by == staff
    assert review.admin_replied_at is not None
    delay.assert_called_once_with(review.pk)


@pytest.mark.django_db
def test_clearing_reply_resets_meta_without_notification(review, staff, rf):
    _save_reply(review, staff, rf, "Ответ")
    delay = _save_reply(review, staff, rf, "   ")

    review.refresh_from_db()
    assert review.admin_reply == ""
    assert review.admin_replied_by is None
    assert review.admin_replied_at is None
    delay.assert_not_called()


@pytest.mark.django_db
def test_reply_is_exposed_in_api(review, staff, rf):
    _save_reply(review, staff, rf, "Спасибо!")
    review.refresh_from_db()

    data = ProductReviewSerializer(review).data

    assert data["admin_reply"] == "Спасибо!"
    assert data["admin_replied_at"]


@pytest.mark.django_db
def test_author_is_notified_about_reply(review, settings):
    from apps.feedback.tasks import notify_review_author_reply

    settings.TELEGRAM_BOT_TOKEN = "token"
    ProductReview.objects.filter(pk=review.pk).update(admin_reply="Спасибо, рады помочь!")
    with patch("apps.feedback.tasks.requests.post") as post:
        post.return_value = SimpleNamespace(ok=True, status_code=200)
        notify_review_author_reply.run(review.pk)

    payload = post.call_args.kwargs["json"]
    assert payload["chat_id"] == "999"
    assert "Reply Product" in payload["text"]
    assert "Спасибо, рады помочь!" in payload["text"]
