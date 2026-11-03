"""Regression contract for the storefront slug lookup of catalog cards."""

from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.http import Http404, QueryDict
from rest_framework.response import Response

from apps.catalog import views as catalog_views
from apps.feedback.models import ProductReview


class NotFound(Exception):
    pass


def make_model(product_type=None):
    attrs = {"DoesNotExist": NotFound}
    if product_type is not None:
        attrs["_domain_product_type"] = product_type
    return type("FakeModel", (), attrs)


class FakeQuerySet:
    """Records every slug the mixin tries, in order."""

    def __init__(self, model, stored_slugs):
        self.model = model
        self.stored_slugs = set(stored_slugs)
        self.tried = []

    def get(self, **lookup):
        ((field, value),) = lookup.items()
        assert field == "slug"
        self.tried.append(value)
        if value in self.stored_slugs:
            return SimpleNamespace(slug=value)
        raise self.model.DoesNotExist


class FallbackBase:
    """Stands in for GenericAPIView: get_object() is the final 404."""

    list_payload = None

    def get_object(self):
        raise Http404("fallback")

    def list(self, request, *args, **kwargs):
        return Response(self.list_payload)


class LookupView(catalog_views.SmartSlugLookupMixin, FallbackBase):
    lookup_field = "slug"
    lookup_url_kwarg = None

    def __init__(self, queryset=None, slug=None, list_payload=None):
        self.queryset = queryset
        self.kwargs = {"slug": slug} if slug is not None else {}
        self.list_payload = list_payload

    def get_queryset(self):
        return self.queryset


def resolve(stored_slugs, slug, product_type=None):
    queryset = FakeQuerySet(make_model(product_type), stored_slugs)
    obj = LookupView(queryset, slug).get_object()
    return obj.slug, queryset.tried


def test_old_import_path_is_exact_alias():
    from apps.catalog import product_resolution

    assert catalog_views.SmartSlugLookupMixin is product_resolution.SmartSlugLookupMixin
    assert catalog_views._get_public_variant is product_resolution.get_public_variant
    assert (
        catalog_views._resolve_active_variant_from_request
        is product_resolution.resolve_active_variant_from_request
    )


def test_exact_slug_wins_first():
    assert resolve({"cap", "cap-cap"}, "cap") == ("cap", ["cap"])


def test_short_url_finds_doubled_slug_in_db():
    assert resolve({"cap-cap"}, "cap") == ("cap-cap", ["cap", "cap-cap"])


def test_domain_prefix_is_added_with_underscores_as_dashes():
    assert resolve({"islamic-clothing-cap"}, "cap", "islamic_clothing") == (
        "islamic-clothing-cap",
        ["cap", "cap-cap", "islamic-clothing-cap"],
    )


def test_domain_prefix_with_doubled_slug():
    assert resolve({"headwear-cap-headwear-cap"}, "cap", "headwear") == (
        "headwear-cap-headwear-cap",
        ["cap", "cap-cap", "headwear-cap", "headwear-cap-headwear-cap"],
    )


def test_doubled_url_finds_short_slug_in_db():
    assert resolve({"red-cap"}, "red-cap-red-cap") == (
        "red-cap",
        ["red-cap-red-cap", "red-cap-red-cap-red-cap-red-cap", "red-cap"],
    )


def test_prefixed_url_finds_slug_without_prefix():
    assert resolve({"cap"}, "Headwear-cap", "headwear") == (
        "cap",
        ["Headwear-cap", "Headwear-cap-Headwear-cap", "cap"],
    )


def test_model_without_domain_type_skips_prefix_steps():
    queryset = FakeQuerySet(make_model(), {"cap"})
    with pytest.raises(Http404):
        LookupView(queryset, "headwear-cap").get_object()
    assert queryset.tried == ["headwear-cap", "headwear-cap-headwear-cap"]


def test_odd_or_asymmetric_parts_are_not_halved():
    queryset = FakeQuerySet(make_model(), set())
    with pytest.raises(Http404):
        LookupView(queryset, "a-b-a").get_object()
    with pytest.raises(Http404):
        LookupView(queryset, "a-b-c-d").get_object()
    assert queryset.tried == ["a-b-a", "a-b-a-a-b-a", "a-b-c-d", "a-b-c-d-a-b-c-d"]


def test_nothing_found_falls_back_to_base_404():
    queryset = FakeQuerySet(make_model("headwear"), set())
    with pytest.raises(Http404):
        LookupView(queryset, "cap").get_object()
    assert queryset.tried == ["cap", "cap-cap", "headwear-cap", "headwear-cap-headwear-cap"]


def test_missing_slug_uses_base_get_object():
    queryset = FakeQuerySet(make_model(), {"cap"})
    with pytest.raises(Http404):
        LookupView(queryset).get_object()
    assert queryset.tried == []


def test_custom_lookup_url_kwarg_is_read():
    queryset = FakeQuerySet(make_model(), {"cap"})
    view = LookupView(queryset)
    view.lookup_url_kwarg = "product_slug"
    view.kwargs = {"product_slug": "cap"}
    assert view.get_object().slug == "cap"


def card_request(query=""):
    return SimpleNamespace(query_params=QueryDict(query))


FULL_ROW = {
    "id": 1,
    "slug": "reviewed-chair",
    "product_type": "furniture",
    "description": "x" * 300,
    "seo_title": "detail only",
}


def test_list_without_card_view_is_untouched():
    payload = {"results": [dict(FULL_ROW)]}
    response = LookupView(list_payload=payload).list(card_request())
    assert response.data["results"][0]["seo_title"] == "detail only"


@pytest.mark.django_db
@pytest.mark.parametrize("paginated", [True, False])
def test_card_view_compacts_rows_and_attaches_reviews(paginated):
    user = get_user_model().objects.create_user(
        email="reviewer@example.com", username="reviewer", password="password"
    )
    ProductReview.objects.create(
        user=user,
        product_type="furniture",
        product_slug="reviewed-chair",
        product_name="Reviewed chair",
        author_name="Review Author",
        rating=5,
        text="Approved",
        status=ProductReview.Status.APPROVED,
    )
    payload = {"count": 1, "results": [dict(FULL_ROW)]} if paginated else [dict(FULL_ROW)]

    response = LookupView(list_payload=payload).list(card_request("view=card"))

    rows = response.data["results"] if paginated else response.data
    assert rows == [{
        "id": 1,
        "slug": "reviewed-chair",
        "product_type": "furniture",
        "description": "x" * 240,
        "rating": 5.0,
        "reviews_count": 1,
    }]
    if paginated:
        assert response.data["count"] == 1


def test_active_variant_prefers_explicit_slug_then_query():
    resolver = catalog_views._resolve_active_variant_from_request
    assert resolver(card_request("active_variant_slug=red"), "blue") == "blue"
    assert resolver(card_request("active_variant_slug=%20red%20")) == "red"
    assert resolver(card_request("active_variant_slug=%20")) is None
    assert resolver(card_request()) is None
