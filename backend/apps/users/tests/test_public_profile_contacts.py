from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from apps.users.models import User
from apps.users.serializers import PublicUserProfileSerializer


class PublicProfileContactTests(SimpleTestCase):
    def setUp(self):
        self.user = User(
            username="public-contact",
            email="public@example.com",
            google_id="google-auth-subject",
            is_public_profile=True,
            show_email=True,
        )
        self.request = APIRequestFactory().get("/api/users/public-profile/")
        self.request.user = AnonymousUser()

    def serialize_profile(self):
        with (
            patch.object(PublicUserProfileSerializer, "get_avatar_url", return_value=None),
            patch.object(PublicUserProfileSerializer, "get_total_orders", return_value=0),
            patch.object(PublicUserProfileSerializer, "get_testimonial_id", return_value=None),
        ):
            return PublicUserProfileSerializer(
                self.user,
                context={"request": self.request},
            ).data

    def test_visible_email_is_returned_without_legacy_google_plus_link(self):
        data = self.serialize_profile()

        self.assertEqual(data["email"], "public@example.com")
        self.assertNotIn("google", data["social_links"])
        self.assertNotIn("google-auth-subject", str(data))

    def test_hidden_email_does_not_create_a_public_contact(self):
        self.user.show_email = False
        data = self.serialize_profile()

        self.assertNotIn("email", data)
        self.assertNotIn("google", data["social_links"])
