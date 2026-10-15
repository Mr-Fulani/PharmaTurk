"""Поле WhatsApp в профиле: номер телефона или юзернейм."""

import pytest

from apps.users.models import User
from apps.users.serializers import UserSerializer


def _validate(user, value):
    serializer = UserSerializer(instance=user, data={"whatsapp_phone": value}, partial=True)
    serializer.is_valid()
    return serializer


@pytest.fixture
def user(db):
    return User.objects.create_user(username="wa-user", email="wa@example.test", password="not-used")


def test_whatsapp_phone_still_accepted(user):
    serializer = _validate(user, "+79990001122")

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["whatsapp_phone"] == "+79990001122"


def test_whatsapp_username_is_stored_with_at_prefix(user):
    serializer = _validate(user, "ivan.petrov")

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["whatsapp_phone"] == "@ivan.petrov"


def test_invalid_whatsapp_username_is_rejected(user):
    serializer = _validate(user, "@no spaces!")

    assert not serializer.is_valid()
    assert "whatsapp_phone" in serializer.errors


def test_whatsapp_username_must_be_unique(user):
    User.objects.create_user(username="other", email="o@example.test", password="x", whatsapp_phone="@Ivan.Petrov")

    serializer = _validate(user, "@ivan.petrov")

    assert not serializer.is_valid()
    assert "whatsapp_phone" in serializer.errors
