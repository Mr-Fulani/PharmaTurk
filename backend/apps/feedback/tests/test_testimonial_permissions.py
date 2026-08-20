from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.feedback import views as feedback_views


@pytest.fixture
def request_factory():
    return APIRequestFactory()


@pytest.mark.parametrize(
    ("action", "permission_class"),
    (
        ("list", AllowAny),
        ("retrieve", AllowAny),
        ("create", IsAuthenticated),
        ("update", IsAdminUser),
        ("partial_update", IsAdminUser),
        ("destroy", IsAdminUser),
        ("future_action", IsAdminUser),
    ),
)
def test_testimonial_permission_matrix(action, permission_class):
    view = feedback_views.TestimonialViewSet()
    view.action = action

    permissions = view.get_permissions()

    assert len(permissions) == 1
    assert isinstance(permissions[0], permission_class)


def _dispatch(request_factory, action, method, user=None):
    detail_actions = {"retrieve", "update", "partial_update", "destroy"}
    path = (
        "/api/feedback/testimonials/1/"
        if action in detail_actions
        else "/api/feedback/testimonials/"
    )
    request = getattr(request_factory, method)(path, {}, format="json")
    if user is not None:
        force_authenticate(request, user=user)

    response_status = status.HTTP_201_CREATED if action == "create" else status.HTTP_200_OK
    with patch.object(
        feedback_views.TestimonialViewSet,
        action,
        autospec=True,
        return_value=Response(status=response_status),
    ):
        view = feedback_views.TestimonialViewSet.as_view({method: action})
        kwargs = {"pk": 1} if action in detail_actions else {}
        return view(request, **kwargs)


@pytest.mark.parametrize(("action", "method"), (("list", "get"), ("retrieve", "get")))
def test_testimonial_reads_remain_public(request_factory, action, method):
    response = _dispatch(request_factory, action, method)

    assert response.status_code == status.HTTP_200_OK


def test_testimonial_create_requires_authentication(request_factory):
    response = _dispatch(request_factory, "create", "post")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_authenticated_user_can_create_testimonial(request_factory):
    response = _dispatch(
        request_factory,
        "create",
        "post",
        user=SimpleNamespace(pk=1, is_authenticated=True, is_staff=False),
    )

    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.parametrize(
    ("action", "method"),
    (("update", "put"), ("partial_update", "patch"), ("destroy", "delete")),
)
@pytest.mark.parametrize(
    ("user", "expected_status"),
    (
        (None, status.HTTP_401_UNAUTHORIZED),
        (
            SimpleNamespace(pk=1, is_authenticated=True, is_staff=False),
            status.HTTP_403_FORBIDDEN,
        ),
    ),
)
def test_testimonial_mutations_reject_non_staff(
    request_factory,
    action,
    method,
    user,
    expected_status,
):
    response = _dispatch(request_factory, action, method, user=user)

    assert response.status_code == expected_status


@pytest.mark.parametrize(
    ("action", "method"),
    (("update", "put"), ("partial_update", "patch"), ("destroy", "delete")),
)
def test_testimonial_mutations_allow_staff(request_factory, action, method):
    response = _dispatch(
        request_factory,
        action,
        method,
        user=SimpleNamespace(pk=1, is_authenticated=True, is_staff=True),
    )

    assert response.status_code == status.HTTP_200_OK
