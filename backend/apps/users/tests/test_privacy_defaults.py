from django.test import SimpleTestCase

from apps.users.models import User


class UserPrivacyDefaultTests(SimpleTestCase):
    def test_public_profile_and_contact_sharing_are_opt_in(self):
        for field_name in ("is_public_profile", "show_email", "show_phone"):
            with self.subTest(field=field_name):
                self.assertIs(User._meta.get_field(field_name).default, False)
