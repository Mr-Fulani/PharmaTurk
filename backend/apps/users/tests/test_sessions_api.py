from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.users.models import User, UserSession


@pytest.fixture
def authenticated_client(db):
    user = User.objects.create_user(
        username="sessions-user",
        email="sessions@example.com",
        password="test-only-password",
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.mark.django_db
def test_session_routes_expose_only_their_supported_methods(authenticated_client):
    client, user = authenticated_client
    session = UserSession.objects.create(
        user=user,
        session_key="session-key",
        ip_address="127.0.0.1",
        user_agent="pytest",
        expires_at=timezone.now() + timedelta(days=1),
    )

    assert client.get("/api/users/sessions/").status_code == 200
    assert client.delete("/api/users/sessions/").status_code == 405
    assert client.get(f"/api/users/sessions/{session.pk}/").status_code == 405

    response = client.delete(f"/api/users/sessions/{session.pk}/")
    assert response.status_code == 200
    session.refresh_from_db()
    assert session.is_active is False
