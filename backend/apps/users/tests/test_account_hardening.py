"""Мелкие правки защиты учётных записей (проверка защиты 22.11.2026)."""

from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from api.views import _strip_image_metadata
from apps.orders.throttles import ReceiptEmailBurstThrottle, ReceiptEmailSustainedThrottle
from apps.users.backends import MultiFieldAuthBackend
from apps.users.models import User
from apps.users.serializers import (
    UserEmailVerificationSerializer,
    UserPasswordChangeSerializer,
    UserSerializer,
)

PASSWORD = "old-password-123"


def _user(username="hardening", **extra):
    return User.objects.create_user(
        username=username, email=f"{username}@example.test", password=PASSWORD, **extra
    )


@pytest.mark.django_db
def test_wrong_verification_codes_burn_the_code_after_five_attempts():
    user = _user(verification_code="123456")

    for _attempt in range(5):
        serializer = UserEmailVerificationSerializer(
            data={"email": user.email, "verification_code": "000000"}
        )
        assert not serializer.is_valid()

    user.refresh_from_db()
    assert user.verification_code == ""
    correct = UserEmailVerificationSerializer(
        data={"email": user.email, "verification_code": "123456"}
    )
    assert not correct.is_valid()


@pytest.mark.django_db
def test_correct_verification_code_still_works_after_a_few_mistakes():
    user = _user("verify-ok", verification_code="654321")
    for _attempt in range(3):
        assert not UserEmailVerificationSerializer(
            data={"email": user.email, "verification_code": "000000"}
        ).is_valid()

    serializer = UserEmailVerificationSerializer(
        data={"email": user.email, "verification_code": "654321"}
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["user"] == user


@pytest.mark.django_db
def test_empty_stored_code_never_matches():
    user = _user("verify-empty")

    assert not UserEmailVerificationSerializer(
        data={"email": user.email, "verification_code": "000000"}
    ).is_valid()


@pytest.mark.django_db
def test_password_change_revokes_old_refresh_tokens_and_keeps_this_device():
    user = _user("pwd-change")
    old_refresh = RefreshToken.for_user(user)
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/users/change-password/",
        {
            "current_password": PASSWORD,
            "new_password": "new-password-456",
            "new_password_confirm": "new-password-456",
        },
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.data["tokens"]["access"]
    assert "refresh_token" in response.cookies
    anonymous = APIClient()
    assert anonymous.post(
        "/api/auth/jwt/refresh/", {"refresh": str(old_refresh)}, format="json"
    ).status_code == 401
    assert anonymous.post(
        "/api/auth/jwt/refresh/",
        {"refresh": response.cookies["refresh_token"].value},
        format="json",
    ).status_code == 200


def test_password_change_requires_letters_and_digits():
    user = SimpleNamespace(check_password=lambda value: value == PASSWORD)
    serializer = UserPasswordChangeSerializer(
        data={
            "current_password": PASSWORD,
            "new_password": "onlyletters",
            "new_password_confirm": "onlyletters",
        },
        context={"request": SimpleNamespace(user=user)},
    )

    assert not serializer.is_valid()


def test_avatar_is_not_writable_through_profile_update():
    assert UserSerializer().fields["avatar"].read_only is True


@pytest.mark.django_db
def test_phone_login_needs_the_full_number():
    _user("phone-owner", phone_number="+905551112233")
    backend = MultiFieldAuthBackend()

    assert backend.authenticate(None, username="5551", password=PASSWORD) is None
    assert backend.authenticate(None, username="905551112233", password=PASSWORD) is not None
    # Другой формат записи того же номера по-прежнему находится.
    assert backend.authenticate(None, username="05551112233", password=PASSWORD) is not None


@pytest.mark.django_db
def test_phone_login_refuses_an_ambiguous_tail():
    _user("phone-a", phone_number="+905551112233")
    _user("phone-b", phone_number="+75551112233")

    assert MultiFieldAuthBackend().authenticate(None, username="85551112233", password=PASSWORD) is None


def test_receipt_email_limits_count_in_their_own_buckets():
    scopes = {ReceiptEmailBurstThrottle.scope, ReceiptEmailSustainedThrottle.scope}

    assert len(scopes) == 2
    assert "user" not in scopes


def test_search_photo_loses_exif_but_keeps_pixels():
    source = Image.new("RGB", (32, 16), color=(10, 120, 200))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"
    with_exif = BytesIO()
    source.save(with_exif, format="JPEG", exif=exif.tobytes())

    cleaned = _strip_image_metadata(with_exif.getvalue(), "JPEG")

    result = Image.open(BytesIO(cleaned))
    assert not result.getexif()
    assert result.size == (32, 16)


def test_photo_without_exif_is_left_untouched():
    plain = BytesIO()
    Image.new("RGB", (8, 8)).save(plain, format="PNG")

    assert _strip_image_metadata(plain.getvalue(), "PNG") == plain.getvalue()
