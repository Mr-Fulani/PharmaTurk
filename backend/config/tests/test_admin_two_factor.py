"""Второй фактор входа в Django Admin (docs/ADMIN_TWO_FACTOR.md)."""

import time

import pytest
from django.test import Client, override_settings
from django_otp.oath import TOTP
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.users.models import User

PASSWORD = "test-only-password-2fa"


@pytest.fixture
def staff(db):
    return User.objects.create_user(
        username="otp-staff",
        email="otp-staff@example.test",
        password=PASSWORD,
        is_staff=True,
        is_superuser=True,
    )


def _current_code(device):
    totp = TOTP(device.bin_key, device.step, device.t0, device.digits, device.drift)
    totp.time = time.time()
    return str(totp.token()).zfill(device.digits)


def _login(client, **extra):
    return client.post(
        "/admin/login/",
        {"username": "otp-staff@example.test", "password": PASSWORD, "next": "/admin/", **extra},
    )


@pytest.mark.django_db
def test_staff_without_device_logs_in_with_password_only(staff):
    client = Client()

    response = _login(client)

    assert response.status_code == 302
    assert client.get("/admin/").status_code == 200


@pytest.mark.django_db
def test_staff_with_device_needs_the_code(staff):
    device = TOTPDevice.objects.create(user=staff, name="phone", confirmed=True)
    client = Client()

    without_code = _login(client)
    assert without_code.status_code == 200
    assert client.get("/admin/").status_code == 302

    wrong_code = _login(client, otp_token="000000")
    assert wrong_code.status_code == 200
    assert client.get("/admin/").status_code == 302

    device.refresh_from_db()
    device.throttle_reset()
    with_code = _login(client, otp_token=_current_code(device))
    assert with_code.status_code == 302
    assert client.get("/admin/").status_code == 200


@pytest.mark.django_db
def test_session_without_code_is_not_enough_once_device_exists(staff):
    client = Client()
    client.force_login(staff)
    assert client.get("/admin/").status_code == 200

    TOTPDevice.objects.create(user=staff, name="phone", confirmed=True)

    response = client.get("/admin/")
    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]


@pytest.mark.django_db
def test_backup_code_works_once(staff):
    TOTPDevice.objects.create(user=staff, name="phone", confirmed=True)
    backup = StaticDevice.objects.create(user=staff, name="backup", confirmed=True)
    StaticToken.objects.create(device=backup, token="abcd2345")

    first = Client()
    assert _login(first, otp_token="abcd2345").status_code == 302
    assert first.get("/admin/").status_code == 200

    second = Client()
    assert _login(second, otp_token="abcd2345").status_code == 200
    assert second.get("/admin/").status_code == 302


@pytest.mark.django_db
@override_settings(ADMIN_OTP_REQUIRED=True)
def test_required_mode_refuses_staff_without_device(staff):
    client = Client()

    assert _login(client).status_code == 200
    assert client.get("/admin/").status_code == 302


@pytest.mark.django_db
def test_staff_enables_second_factor_only_with_a_valid_code(staff):
    client = Client()
    client.force_login(staff)

    page = client.get("/admin/two-factor/")
    assert page.status_code == 200
    assert "data:image/svg+xml;base64," in page.content.decode()
    device = TOTPDevice.objects.get(user=staff)
    assert device.confirmed is False

    wrong = client.post("/admin/two-factor/", {"otp_token": "000000"})
    assert wrong.status_code == 200
    device.refresh_from_db()
    assert device.confirmed is False
    assert client.get("/admin/").status_code == 200

    device.throttle_reset()
    done = client.post("/admin/two-factor/", {"otp_token": _current_code(device)})
    assert done.status_code == 200
    device.refresh_from_db()
    assert device.confirmed is True
    assert StaticToken.objects.filter(device__user=staff).count() == 5
    # Эта же сессия остаётся в админке, новая — без кода не входит.
    assert client.get("/admin/").status_code == 200
    assert _login(Client()).status_code == 200
