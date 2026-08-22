import pytest
from django.urls import reverse
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory

from apps.pages.models import Page
from apps.pages.views import PageDetailView, PageListView


def _has_active_publication_filter(queryset) -> bool:
    """Inspect the ORM query without opening a database connection."""
    pending = [queryset.query.where]
    while pending:
        node = pending.pop()
        pending.extend(getattr(node, "children", ()))
        lhs = getattr(node, "lhs", None)
        target = getattr(lhs, "target", None)
        if getattr(target, "name", None) == "is_active" and getattr(node, "rhs", None) is True:
            return True
    return False


def test_page_detail_queryset_is_scoped_to_active_pages_without_database_access():
    queryset = PageDetailView().get_queryset()

    assert _has_active_publication_filter(queryset)


@pytest.mark.django_db
def test_public_page_detail_returns_active_page_and_hides_inactive_page():
    active = Page.objects.create(
        slug="published-security-page",
        title_ru="Опубликовано",
        content_ru="Публичный текст",
        is_active=True,
    )
    inactive = Page.objects.create(
        slug="unpublished-security-page",
        title_ru="Черновик",
        content_ru="Непубличный текст",
        is_active=False,
    )
    client = APIClient()

    published_response = client.get(reverse("page-detail", kwargs={"slug": active.slug}))
    unpublished_response = client.get(reverse("page-detail", kwargs={"slug": inactive.slug}))

    assert published_response.status_code == 200
    assert published_response.json()["slug"] == active.slug
    assert unpublished_response.status_code == 404
    assert "Непубличный текст" not in str(unpublished_response.json())


def test_page_list_query_language_overrides_stale_language_header():
    request = Request(
        APIRequestFactory().get("/api/pages/?lang=en", HTTP_X_LANGUAGE="ru")
    )
    view = PageListView()
    view.request = request
    view.args = ()
    view.kwargs = {}
    view.format_kwarg = None

    context = view.get_serializer_context()

    assert context["lang"] == "en"
