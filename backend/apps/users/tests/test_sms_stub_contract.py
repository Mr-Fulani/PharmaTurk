from rest_framework import status
from rest_framework.test import APIRequestFactory

from apps.users.serializers import SocialAuthSerializer
from apps.users.views import SMSSendCodeView


def test_sms_send_stub_reports_not_implemented_instead_of_false_success():
    request = APIRequestFactory().post(
        "/api/users/sms/send-code/",
        {"phone_number": "+79991234567"},
        format="json",
        REMOTE_ADDR="203.0.113.90",
    )

    response = SMSSendCodeView.as_view()(request)

    assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
    assert "phone_number" not in response.data


def test_social_auth_contract_rejects_unimplemented_providers():
    serializer = SocialAuthSerializer(
        data={"provider": "facebook", "access_token": "not-used"}
    )

    assert not serializer.is_valid()
    assert "provider" in serializer.errors


def test_social_auth_contract_bounds_provider_payloads():
    serializer = SocialAuthSerializer(
        data={"provider": "vk", "access_token": "x" * 8193}
    )

    assert not serializer.is_valid()
    assert "access_token" in serializer.errors
