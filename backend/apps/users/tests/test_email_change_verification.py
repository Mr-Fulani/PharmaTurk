from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework import serializers

from apps.users.models import User
from apps.users.serializers import UserSerializer


class EmailChangeResetsVerificationTests(SimpleTestCase):
    """Смена email в профиле не должна оставлять адрес «подтверждённым»."""

    def _update(self, user, data):
        with patch.object(serializers.ModelSerializer, "update", return_value=user):
            return UserSerializer().update(user, data)

    def test_new_email_becomes_unverified(self):
        user = User(email="owner@example.com", is_verified=True)

        self._update(user, {"email": "victim@example.com"})

        self.assertFalse(user.is_verified)

    def test_same_email_in_other_case_stays_verified(self):
        user = User(email="owner@example.com", is_verified=True)

        self._update(user, {"email": "Owner@Example.com"})

        self.assertTrue(user.is_verified)

    def test_update_without_email_stays_verified(self):
        user = User(email="owner@example.com", is_verified=True)

        self._update(user, {"first_name": "Anna"})

        self.assertTrue(user.is_verified)
