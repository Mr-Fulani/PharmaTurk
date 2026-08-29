from decimal import Decimal
from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product


@pytest.mark.django_db
def test_similar_products_stay_in_same_type_and_category():
    supplements = Category.objects.create(name="Supplements", slug="similar-supplements")
    other_supplements = Category.objects.create(
        name="Other supplements",
        slug="other-similar-supplements",
    )
    target = Product.objects.create(
        name="Target supplement",
        slug="target-similar-supplement",
        product_type="supplements",
        category=supplements,
        price=Decimal("100.00"),
        is_active=True,
    )
    matching = Product.objects.create(
        name="Matching supplement",
        slug="matching-similar-supplement",
        product_type="supplements",
        category=supplements,
        price=Decimal("90.00"),
        is_active=True,
    )
    wrong_type = Product.objects.create(
        name="Unrelated clothing",
        slug="unrelated-similar-clothing",
        product_type="clothing",
        category=supplements,
        price=Decimal("80.00"),
        is_active=True,
    )
    wrong_category = Product.objects.create(
        name="Wrong supplement category",
        slug="wrong-similar-supplement-category",
        product_type="supplements",
        category=other_supplements,
        price=Decimal("70.00"),
        is_active=True,
    )
    rows = [
        {"product": {"id": product.pk, "slug": product.slug, "product_type": product.product_type}}
        for product in (matching, wrong_type, wrong_category)
    ]

    with (
        patch(
            "apps.recommendations.services.vector_engine.QdrantRecommendationEngine"
        ) as engine_class,
        patch(
            "apps.recommendations.services.reranker.BusinessReranker"
        ) as reranker_class,
        patch("apps.recommendations.tasks.log_recommendation_event.delay"),
    ):
        engine_class.return_value.find_similar.return_value = rows
        reranker_class.return_value.rerank.return_value = rows
        response = APIClient().get(
            reverse("product-similar", kwargs={"slug": target.slug}),
        )

    assert response.status_code == 200
    assert [row["product"]["id"] for row in response.data["results"]] == [matching.pk]
    assert engine_class.return_value.find_similar.call_args.kwargs["filters"] == {
        "category_id": supplements.pk,
    }
