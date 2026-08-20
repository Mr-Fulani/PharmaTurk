from types import SimpleNamespace

from django.urls import resolve

from api.throttles import (
    LOGIN_THROTTLES,
    REGISTRATION_THROTTLES,
    TOKEN_THROTTLES,
    VERIFICATION_THROTTLES,
    LoginBurstThrottle,
    LoginSustainedThrottle,
    RegistrationBurstThrottle,
    RegistrationSustainedThrottle,
    TokenBurstThrottle,
    TokenSustainedThrottle,
    VerificationBurstThrottle,
    VerificationSustainedThrottle,
    get_trusted_client_ip,
)
from api.views import JWTObtainPairView, JWTRefreshView, JWTVerifyView
from apps.users.views import (
    SocialAuthView,
    TelegramAuthView,
    UserEmailVerificationView,
    UserLoginView,
    UserRegistrationView,
    UserRequestVerificationCodeView,
)


def _request(**meta):
    return SimpleNamespace(META=meta)


def test_auth_throttle_rates_are_explicit_and_independent():
    assert LoginBurstThrottle().parse_rate(LoginBurstThrottle.rate) == (5, 60)
    assert LoginSustainedThrottle().parse_rate(LoginSustainedThrottle.rate) == (50, 86400)
    assert TokenBurstThrottle().parse_rate(TokenBurstThrottle.rate) == (30, 60)
    assert TokenSustainedThrottle().parse_rate(TokenSustainedThrottle.rate) == (500, 86400)
    assert RegistrationBurstThrottle().parse_rate(RegistrationBurstThrottle.rate) == (3, 3600)
    assert RegistrationSustainedThrottle().parse_rate(RegistrationSustainedThrottle.rate) == (10, 86400)
    assert VerificationBurstThrottle().parse_rate(VerificationBurstThrottle.rate) == (5, 60)
    assert VerificationSustainedThrottle().parse_rate(VerificationSustainedThrottle.rate) == (30, 86400)


def test_auth_throttle_uses_nginx_overwritten_real_ip_not_x_forwarded_for():
    throttle = LoginBurstThrottle()
    key = throttle.get_cache_key(
        _request(
            HTTP_X_REAL_IP="203.0.113.7",
            HTTP_X_FORWARDED_FOR="10.0.0.1, 10.0.0.2",
            REMOTE_ADDR="172.18.0.2",
        ),
        None,
    )

    assert key is not None
    assert "203.0.113.7" in key
    assert "10.0.0.1" not in key
    assert get_trusted_client_ip(
        _request(
            HTTP_X_FORWARDED_FOR="198.51.100.99",
            REMOTE_ADDR="203.0.113.8",
        )
    ) == "203.0.113.8"


def test_auth_views_apply_the_expected_throttle_sets():
    assert JWTObtainPairView.throttle_classes == LOGIN_THROTTLES
    assert UserLoginView.throttle_classes == LOGIN_THROTTLES
    assert JWTRefreshView.throttle_classes == TOKEN_THROTTLES
    assert JWTVerifyView.throttle_classes == TOKEN_THROTTLES
    assert UserRegistrationView.throttle_classes == REGISTRATION_THROTTLES
    assert SocialAuthView.throttle_classes == LOGIN_THROTTLES
    assert TelegramAuthView.throttle_classes == LOGIN_THROTTLES
    assert UserEmailVerificationView.throttle_classes == VERIFICATION_THROTTLES
    assert UserRequestVerificationCodeView.throttle_classes == VERIFICATION_THROTTLES


def test_all_token_routes_use_hardened_views():
    assert resolve("/api/auth/jwt/create/").func.view_class is JWTObtainPairView
    assert resolve("/api/auth/jwt/refresh").func.view_class is JWTRefreshView
    assert resolve("/api/users/token/").func.view_class is JWTObtainPairView
    assert resolve("/api/users/token/refresh/").func.view_class is JWTRefreshView
    assert resolve("/api/users/token/verify/").func.view_class is JWTVerifyView
