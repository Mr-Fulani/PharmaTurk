from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.users import social_auth, views


class _RefreshToken:
    access_token = "access-token"

    def __str__(self):
        return "refresh-token"


def _authenticated_user(**overrides):
    values = {
        "id": 7,
        "pk": 7,
        "is_authenticated": True,
        "email": "tg_123@mudaroba.local",
        "is_verified": False,
        "first_name": "",
        "last_name": "",
        "google_id": None,
        "save": MagicMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _provider(user_info):
    return SimpleNamespace(
        name="google",
        id_field="google_id",
        get_user_info=MagicMock(return_value=user_info),
    )


def _request(user):
    request = APIRequestFactory().post(
        "/api/users/social-auth/",
        {"provider": "google", "access_token": "google.id.token"},
        format="json",
        REMOTE_ADDR="127.0.0.1",
    )
    force_authenticate(request, user=user)
    return request


class AuthenticatedSocialLinkSecurityTests(SimpleTestCase):
    def _call_view(self, user, user_info, user_manager):
        provider = _provider(user_info)
        serializer = MagicMock()
        serializer.return_value.data = {"id": user.id}

        with (
            patch.dict(social_auth.PROVIDERS, {"google": lambda: provider}, clear=True),
            patch.object(views.User, "objects", user_manager),
            patch.object(views, "UserSerializer", serializer),
            patch.object(views, "create_user_session"),
            patch.object(views, "link_guest_orders_for_verified_user") as order_claim,
            patch.object(views.RefreshToken, "for_user", return_value=_RefreshToken()),
            patch.object(views.SocialAuthView, "throttle_classes", []),
        ):
            response = views.SocialAuthView.as_view()(_request(user))

        return response, order_claim

    def test_verified_provider_email_promotes_placeholder_before_order_claim(self):
        user = _authenticated_user()
        manager = MagicMock()
        manager.filter.return_value.exclude.return_value.first.return_value = None
        manager.filter.return_value.exclude.return_value.exists.return_value = False

        response, order_claim = self._call_view(
            user,
            {
                "provider_id": "google-user",
                "email": "buyer@example.com",
                "email_verified": True,
                "first_name": "Buyer",
                "last_name": "",
                "avatar_url": None,
            },
            manager,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(user.google_id, "google-user")
        self.assertEqual(user.email, "buyer@example.com")
        self.assertTrue(user.is_verified)
        user.save.assert_any_call(
            update_fields=["google_id", "first_name", "email", "is_verified"]
        )
        order_claim.assert_called_once_with(user)

    def test_unverified_provider_email_is_not_applied_to_authenticated_user(self):
        user = _authenticated_user()
        manager = MagicMock()
        manager.filter.return_value.exclude.return_value.first.return_value = None

        response, order_claim = self._call_view(
            user,
            {
                "provider_id": "google-user",
                "email": "victim@example.com",
                "email_verified": False,
                "first_name": "",
                "last_name": "",
                "avatar_url": None,
            },
            manager,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(user.email, "tg_123@mudaroba.local")
        self.assertFalse(user.is_verified)
        user.save.assert_any_call(update_fields=["google_id"])
        order_claim.assert_called_once_with(user)

    def test_verified_email_owned_by_another_account_rejects_link(self):
        user = _authenticated_user()
        manager = MagicMock()

        provider_lookup = MagicMock()
        provider_lookup.exclude.return_value.first.return_value = None
        email_lookup = MagicMock()
        email_lookup.exclude.return_value.exists.return_value = True

        def filter_users(**criteria):
            if criteria == {"google_id": "google-user"}:
                return provider_lookup
            if criteria == {"email__iexact": "owner@example.com"}:
                return email_lookup
            raise AssertionError(f"Unexpected lookup: {criteria}")

        manager.filter.side_effect = filter_users

        response, order_claim = self._call_view(
            user,
            {
                "provider_id": "google-user",
                "email": "owner@example.com",
                "email_verified": True,
                "first_name": "",
                "last_name": "",
                "avatar_url": None,
            },
            manager,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIsNone(user.google_id)
        user.save.assert_not_called()
        order_claim.assert_not_called()
