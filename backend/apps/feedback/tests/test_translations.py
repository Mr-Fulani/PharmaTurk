"""Переводы отзывов и вопросов: админ заполняет, сайт отдаёт на языке запроса."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.feedback.models import (
    ProductQuestion,
    ProductQuestionTranslation,
    ProductReview,
    ProductReviewTranslation,
    Testimonial,
    TestimonialTranslation,
)
from apps.feedback.serializers import TestimonialSerializer
from apps.users.models import User

TARGET = {"product_type": "medicines", "product_slug": "tr-product"}


@pytest.fixture
def author(db):
    return User.objects.create_user(email="tr@example.com", username="tr-author", password="x")


@pytest.fixture
def review(author):
    review = ProductReview.objects.create(
        user=author, product_name="Tr Product", author_name="Автор", rating=5,
        text="Отличный товар", admin_reply="Спасибо!", status=ProductReview.Status.APPROVED, **TARGET,
    )
    ProductReviewTranslation.objects.create(review=review, locale="en", text="Great product", admin_reply="")
    return review


@pytest.mark.django_db
def test_review_is_translated_for_english_and_falls_back_per_field(review):
    en = APIClient().get("/api/feedback/product-reviews/", TARGET, HTTP_ACCEPT_LANGUAGE="en")
    ru = APIClient().get("/api/feedback/product-reviews/", TARGET, HTTP_ACCEPT_LANGUAGE="ru")

    assert en.data["reviews"][0]["text"] == "Great product"
    # перевод ответа не заполнен — показываем оригинал
    assert en.data["reviews"][0]["admin_reply"] == "Спасибо!"
    assert ru.data["reviews"][0]["text"] == "Отличный товар"


@pytest.mark.django_db
def test_author_gets_original_text_for_editing_and_edit_drops_stale_translation(review, author):
    ProductReviewTranslation.objects.filter(review=review).update(admin_reply="Thanks!")
    client = APIClient()
    client.force_authenticate(author)

    own = client.get("/api/feedback/product-reviews/", TARGET, HTTP_ACCEPT_LANGUAGE="en")
    assert own.data["own_review"]["text"] == "Отличный товар"

    with patch("apps.feedback.views.notify_admin_product_review.delay"), patch(
        "apps.catalog.services.product_resolve.resolve_product_payload",
        return_value=({"slug": "tr-product", "name": "Tr Product"}, "generic_product", "medicines"),
    ):
        updated = client.patch(f"/api/feedback/product-reviews/{review.pk}/", {"text": "Новый текст"}, format="json")
    assert updated.status_code == 200, updated.data

    translation = ProductReviewTranslation.objects.get(review=review)
    assert translation.text == ""
    assert translation.admin_reply == "Thanks!"


@pytest.mark.django_db
def test_question_and_answer_are_translated(author):
    question = ProductQuestion.objects.create(
        user=author, product_name="Tr Product", author_name="Автор", question="Есть доставка?",
        answer="Да", status=ProductQuestion.Status.ANSWERED, **TARGET,
    )
    ProductQuestionTranslation.objects.create(
        product_question=question, locale="en", question="Is delivery available?", answer="Yes",
    )

    response = APIClient().get("/api/feedback/product-questions/", TARGET, HTTP_ACCEPT_LANGUAGE="en")

    assert response.data["questions"][0]["question"] == "Is delivery available?"
    assert response.data["questions"][0]["answer"] == "Yes"


@pytest.mark.django_db
def test_testimonial_is_translated(author):
    testimonial = Testimonial.objects.create(user=author, author_name="Автор", text="Всё пришло", rating=5)
    TestimonialTranslation.objects.create(testimonial=testimonial, locale="en", text="Everything arrived")

    data = TestimonialSerializer(testimonial, context={"request": SimpleNamespace(LANGUAGE_CODE="en")}).data

    assert data["text"] == "Everything arrived"


@pytest.mark.django_db
def test_admin_change_pages_show_translation_inlines(review, author, client, settings):
    # В CI нет collectstatic — шаблонам админки нужна статика без манифеста
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    question = ProductQuestion.objects.create(
        user=author, product_name="Tr Product", author_name="Автор", question="Вопрос", **TARGET,
    )
    testimonial = Testimonial.objects.create(user=author, author_name="Автор", text="Текст", rating=5)
    admin_user = User.objects.create_user(
        email="tr-admin@example.com", username="tr-admin", password="x", is_staff=True, is_superuser=True,
    )
    client.force_login(admin_user)

    for url in (
        f"/admin/feedback/productreview/{review.pk}/change/",
        f"/admin/feedback/productquestion/{question.pk}/change/",
        f"/admin/feedback/testimonial/{testimonial.pk}/change/",
    ):
        response = client.get(url)
        assert response.status_code == 200, url
        assert "Переводы" in response.content.decode(), url
