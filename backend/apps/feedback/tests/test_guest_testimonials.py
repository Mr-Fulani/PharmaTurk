"""Отзыв о сервисе без входа в аккаунт: приём, проверка перед показом, защита от спама."""
from unittest.mock import patch

import pytest
from django.contrib import admin
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient

from apps.feedback.models import Testimonial, TestimonialMedia, TestimonialSectionSettings
from apps.feedback.serializers import TESTIMONIAL_TEXT_MAX_LENGTH
from apps.feedback.tasks import notify_admin_testimonial
from apps.users.models import User

URL = "/api/feedback/testimonials/"


@pytest.fixture(autouse=True)
def notify():
    with patch("apps.feedback.views.notify_admin_testimonial.delay") as mocked:
        yield mocked


def payload(**extra):
    return {"author_name": "Айгуль", "text": "Всё пришло вовремя, спасибо!", "rating": 5, **extra}


@pytest.mark.django_db
def test_guest_testimonial_is_saved_unpublished_and_owner_is_notified(notify):
    response = APIClient().post(URL, payload(), format="json")

    assert response.status_code == status.HTTP_201_CREATED
    testimonial = Testimonial.objects.get()
    assert testimonial.user is None
    assert testimonial.author_name == "Айгуль"
    assert testimonial.rating == 5
    assert testimonial.is_active is False
    notify.assert_called_once_with(testimonial.pk)


@pytest.mark.django_db
def test_unpublished_guest_testimonial_is_hidden_until_owner_publishes():
    client = APIClient()
    client.post(URL, payload(), format="json")
    testimonial = Testimonial.objects.get()

    assert client.get(URL).json() == []
    assert client.get(f"{URL}{testimonial.pk}/").status_code == status.HTTP_404_NOT_FOUND
    assert client.get("/api/feedback/reviews-feed/").json()["results"] == []

    from apps.feedback.admin import TestimonialAdmin

    with patch.object(TestimonialAdmin, "message_user"):
        TestimonialAdmin(Testimonial, admin.site).publish_testimonials(
            None, Testimonial.objects.all()
        )

    assert [item["id"] for item in client.get(URL).json()] == [testimonial.pk]
    assert len(client.get("/api/feedback/reviews-feed/").json()["results"]) == 1


@pytest.mark.django_db
def test_guest_cannot_publish_own_testimonial_or_attach_account():
    user = User.objects.create_user(email="u@example.com", username="someone", password="password")

    APIClient().post(URL, payload(is_active=True, user=user.pk), format="json")

    testimonial = Testimonial.objects.get()
    assert testimonial.is_active is False
    assert testimonial.user is None


@pytest.mark.django_db
def test_filled_trap_field_looks_accepted_but_saves_nothing(notify):
    response = APIClient().post(URL, payload(website="https://spam.example"), format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert not Testimonial.objects.exists()
    notify.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "broken",
    (
        {"author_name": ""},
        {"author_name": "И" * 101},
        {"text": ""},
        {"text": "я" * (TESTIMONIAL_TEXT_MAX_LENGTH + 1)},
        {"rating": 6},
    ),
)
def test_guest_testimonial_validates_name_text_and_rating(broken):
    response = APIClient().post(URL, payload(**broken), format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert not Testimonial.objects.exists()


@pytest.mark.django_db
def test_guest_files_are_not_saved():
    data = payload(
        media_type_0="image",
        media_image_0=SimpleUploadedFile("a.jpg", b"not-an-image", content_type="image/jpeg"),
    )

    response = APIClient().post(URL, data, format="multipart")

    assert response.status_code == status.HTTP_201_CREATED
    assert not TestimonialMedia.objects.exists()


@pytest.mark.django_db
def test_guest_submissions_are_limited_per_address():
    client = APIClient()
    statuses = [
        client.post(URL, payload(), format="json", HTTP_X_REAL_IP="203.0.113.7").status_code
        for _ in range(3)
    ]

    assert statuses == [201, 201, 429]
    assert Testimonial.objects.count() == 2
    # Другой адрес считается отдельно; подставной X-Forwarded-For лимит не обходит.
    other = client.post(URL, payload(), format="json", HTTP_X_REAL_IP="203.0.113.8")
    spoofed = client.post(
        URL, payload(), format="json", HTTP_X_REAL_IP="203.0.113.7", HTTP_X_FORWARDED_FOR="198.51.100.1"
    )
    assert other.status_code == status.HTTP_201_CREATED
    assert spoofed.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db
def test_guests_are_rejected_when_switched_off():
    TestimonialSectionSettings.objects.update_or_create(
        pk=1, defaults={"allow_guest_testimonials": False}
    )

    response = APIClient().post(URL, payload(), format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert not Testimonial.objects.exists()


@pytest.mark.django_db
def test_signed_in_user_keeps_account_name_and_long_text_is_rejected(notify):
    user = User.objects.create_user(
        email="u@example.com", username="someone", password="password", first_name="Анна"
    )
    client = APIClient()
    client.force_authenticate(user)

    created = client.post(URL, payload(author_name="Чужое имя"), format="json")
    too_long = client.post(URL, payload(text="я" * (TESTIMONIAL_TEXT_MAX_LENGTH + 1)), format="json")

    assert created.status_code == status.HTTP_201_CREATED
    testimonial = Testimonial.objects.get()
    assert (testimonial.user, testimonial.author_name, testimonial.is_active) == (user, "Анна", False)
    notify.assert_called_once_with(testimonial.pk)
    assert too_long.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_owner_notification_names_guest_and_links_to_admin(settings):
    settings.TELEGRAM_BOT_TOKEN = "token"
    settings.TELEGRAM_CHAT_ID = "42"
    settings.SITE_URL = "https://example.test"
    testimonial = Testimonial.objects.create(author_name="Айгуль", text="Спасибо!", rating=4)

    with patch("apps.feedback.tasks.requests.post") as post:
        post.return_value.ok = True
        notify_admin_testimonial(testimonial.pk)

    sent = post.call_args.kwargs["json"]
    assert sent["chat_id"] == "42"
    assert "Айгуль (без входа в аккаунт)" in sent["text"]
    assert f"https://example.test/admin/feedback/testimonial/{testimonial.pk}/change/" in sent["text"]


@pytest.mark.django_db
def test_settings_admin_is_single_record_with_only_the_switch():
    from apps.feedback.admin import TestimonialSectionSettingsAdmin

    model_admin = TestimonialSectionSettingsAdmin(TestimonialSectionSettings, admin.site)
    assert model_admin.fields == ("allow_guest_testimonials",)
    assert model_admin.has_add_permission(None) is True
    TestimonialSectionSettings.load()
    assert model_admin.has_add_permission(None) is False
    assert model_admin.has_delete_permission(None) is False


# --- Отметка «Покупатель»: отзыв по личной ссылке из заявки -----------------

def _order(number, token):
    from apps.orders.models import Order

    return Order.objects.create(number=number, review_token=token, contact_name="Иван Петров")


@pytest.mark.django_db
def test_valid_key_marks_testimonial_as_buyer_but_still_needs_approval():
    order = _order("M-1", "key-" + "a" * 18)
    client = APIClient()

    response = client.post(URL, payload(order_key=order.review_token), format="json")

    testimonial = Testimonial.objects.get()
    assert (testimonial.order, testimonial.is_active) == (order, False)
    assert response.json()["is_buyer"] is True
    assert client.get(URL).json() == []

    Testimonial.objects.update(is_active=True)
    listed = client.get(URL).json()[0]
    feed = client.get("/api/feedback/reviews-feed/").json()["results"][0]
    assert listed["is_buyer"] is True and feed["is_buyer"] is True
    # Заявка, её номер и суммы наружу не отдаются
    for public in (listed, feed):
        assert "order" not in public and "M-1" not in str(public)


@pytest.mark.django_db
@pytest.mark.parametrize("key", ("wrong-key", "", "x" * 500))
def test_wrong_key_is_accepted_as_ordinary_guest_testimonial(key):
    _order("M-1", "key-" + "a" * 18)

    response = APIClient().post(URL, payload(order_key=key), format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert Testimonial.objects.get().order is None
    assert response.json()["is_buyer"] is False


@pytest.mark.django_db
def test_second_testimonial_by_same_link_gets_no_mark_and_other_order_is_separate():
    first, second = _order("M-1", "key-" + "a" * 18), _order("M-2", "key-" + "b" * 18)
    client = APIClient()

    for key in (first.review_token, first.review_token):
        assert client.post(URL, payload(order_key=key), format="json").status_code == 201
    other = APIClient().post(
        URL, payload(order_key=second.review_token), format="json", HTTP_X_REAL_IP="203.0.113.9"
    )

    assert [t.order for t in Testimonial.objects.order_by("pk")] == [first, None, second]
    assert other.json()["is_buyer"] is True


@pytest.mark.django_db
def test_signed_in_user_with_link_also_gets_buyer_mark():
    order = _order("M-1", "key-" + "a" * 18)
    user = User.objects.create_user(email="u@example.com", username="someone", password="password")
    client = APIClient()
    client.force_authenticate(user)

    client.post(URL, payload(order_key=order.review_token), format="json")

    testimonial = Testimonial.objects.get()
    assert (testimonial.user, testimonial.order) == (user, order)


@pytest.mark.django_db
def test_admin_shows_buyer_order_link_and_filter():
    from apps.feedback.admin import BuyerFilter, TestimonialAdmin

    order = _order("M-1", "key-" + "a" * 18)
    buyer = Testimonial.objects.create(author_name="Иван", text="Спасибо", order=order)
    plain = Testimonial.objects.create(author_name="Гость", text="Спасибо")
    model_admin = TestimonialAdmin(Testimonial, admin.site)

    assert f"/admin/orders/order/{order.pk}/change/" in model_admin.buyer_order(buyer)
    assert "Заявка M-1" in model_admin.buyer_order(buyer)
    assert model_admin.buyer_order(plain) == "—"
    for value, expected in (("yes", [buyer]), ("no", [plain])):
        buyer_filter = BuyerFilter(None, {"buyer": [value]}, Testimonial, model_admin)
        assert list(buyer_filter.queryset(None, Testimonial.objects.all())) == expected


@pytest.mark.django_db
def test_owner_notification_names_buyer_order(settings):
    settings.TELEGRAM_BOT_TOKEN = "token"
    settings.TELEGRAM_CHAT_ID = "42"
    testimonial = Testimonial.objects.create(
        author_name="Иван", text="Спасибо", order=_order("M-1", "key-" + "a" * 18)
    )

    with patch("apps.feedback.tasks.requests.post") as post:
        post.return_value.ok = True
        notify_admin_testimonial(testimonial.pk)

    assert "покупатель, заявка M-1" in post.call_args.kwargs["json"]["text"]
