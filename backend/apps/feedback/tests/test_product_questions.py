from unittest.mock import patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.feedback.admin import ProductQuestionAdmin
from apps.feedback.models import ProductQuestion
from apps.feedback.tasks import notify_admin_product_question
from apps.users.models import User


@pytest.fixture
def question_user(db):
    return User.objects.create_user(
        email="questioner@example.com",
        username="questioner",
        password="password",
        first_name="Question",
        last_name="Author",
    )


@pytest.fixture
def resolved_product():
    with patch(
        "apps.catalog.services.product_resolve.resolve_product_payload",
        return_value=({"slug": "test-product", "name": "Test Product"}, "generic_product", "medicines"),
    ):
        yield


def question_payload(**overrides):
    payload = {
        "product_type": "medicines",
        "product_slug": "test-product",
        "product_name": "Ignored client title",
        "question": "Does this product contain gluten?",
        "is_anonymous": True,
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_product_question_requires_authentication(resolved_product):
    response = APIClient().post("/api/feedback/product-questions/", question_payload(), format="json")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_pending_question_is_private_and_notifies_admin(question_user, resolved_product):
    client = APIClient()
    client.force_authenticate(question_user)

    with patch("apps.feedback.views.notify_admin_product_question.delay") as notify:
        created = client.post("/api/feedback/product-questions/", question_payload(), format="json")

    assert created.status_code == status.HTTP_201_CREATED, created.data
    assert created.data["status"] == ProductQuestion.Status.PENDING
    assert created.data["product_name"] == "Test Product"
    notify.assert_called_once_with(created.data["id"])

    public = APIClient().get(
        "/api/feedback/product-questions/",
        {"product_type": "medicines", "product_slug": "test-product"},
    )
    assert public.status_code == status.HTTP_200_OK
    assert public.data["questions_count"] == 0
    assert public.data["questions"] == []
    assert public.data["own_questions"] == []

    own = client.get(
        "/api/feedback/product-questions/",
        {"product_type": "medicines", "product_slug": "test-product"},
    )
    assert own.data["own_questions"][0]["id"] == created.data["id"]
    assert own.data["own_questions"][0]["author_name"] == "Question Author"


@pytest.mark.django_db
def test_answered_question_is_public_and_anonymous(question_user):
    question = ProductQuestion.objects.create(
        user=question_user,
        product_type="medicines",
        product_slug="test-product",
        product_name="Test Product",
        author_name="Question Author",
        is_anonymous=True,
        question="Does this product contain gluten?",
        answer="No, it does not contain gluten.",
        status=ProductQuestion.Status.ANSWERED,
        answered_at=timezone.now(),
    )

    response = APIClient().get(
        "/api/feedback/product-questions/",
        {"product_type": "medicines", "product_slug": "test-product"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["questions_count"] == 1
    assert response.data["questions"][0]["id"] == question.pk
    assert response.data["questions"][0]["author_name"] == ""
    assert response.data["questions"][0]["user_username"] == ""
    assert response.data["questions"][0]["answer"] == "No, it does not contain gluten."


@pytest.mark.django_db
def test_question_pending_limit_prevents_notification_spam(question_user, resolved_product):
    for index in range(3):
        ProductQuestion.objects.create(
            user=question_user,
            product_type="medicines",
            product_slug="test-product",
            product_name="Test Product",
            author_name="Question Author",
            question=f"Pending question number {index}?",
        )
    client = APIClient()
    client.force_authenticate(question_user)

    with patch("apps.feedback.views.notify_admin_product_question.delay") as notify:
        response = client.post("/api/feedback/product-questions/", question_payload(), format="json")

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    notify.assert_not_called()


@pytest.mark.django_db
def test_admin_answer_is_published_automatically(question_user):
    admin_user = User.objects.create_superuser(
        email="admin@example.com",
        username="admin",
        password="password",
    )
    question = ProductQuestion.objects.create(
        user=question_user,
        product_type="medicines",
        product_slug="test-product",
        product_name="Test Product",
        author_name="Question Author",
        question="Does this product contain gluten?",
        answer="No, it does not.",
    )
    request = RequestFactory().post("/admin/feedback/productquestion/")
    request.user = admin_user

    ProductQuestionAdmin(ProductQuestion, AdminSite()).save_model(request, question, form=None, change=True)

    question.refresh_from_db()
    assert question.status == ProductQuestion.Status.ANSWERED
    assert question.answered_by == admin_user
    assert question.answered_at is not None


@pytest.mark.django_db
@override_settings(TELEGRAM_BOT_TOKEN="bot-token", TELEGRAM_CHAT_ID="123", SITE_URL="https://example.com")
def test_product_question_sends_admin_telegram_notification(question_user):
    question = ProductQuestion.objects.create(
        user=question_user,
        product_type="medicines",
        product_slug="test-product",
        product_name="Test Product",
        author_name="Question Author",
        question="Does this product contain gluten?",
    )
    with patch("apps.feedback.tasks.requests.post") as post:
        post.return_value.raise_for_status.return_value = None
        notify_admin_product_question.run(question.pk)

    payload = post.call_args.kwargs["json"]
    assert payload["chat_id"] == "123"
    assert "Новый вопрос о товаре" in payload["text"]
    assert f"/admin/feedback/productquestion/{question.pk}/change/" in payload["text"]
