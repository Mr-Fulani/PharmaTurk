import pytest
from django.core.cache import cache

from apps.catalog.models import Product
from apps.recommendations.tasks import sync_stale_products_to_qdrant


@pytest.mark.django_db
def test_scheduled_sync_submits_small_incremental_batches(monkeypatch):
    cache.delete("recsys:sync-stale:scheduled")
    for index in range(7):
        Product.objects.create(
            name=f"Vector product {index}",
            slug=f"vector-product-{index}",
            product_type="accessories",
            price=10,
            currency="TRY",
            external_id=f"vector-product-{index}",
            external_data={},
        )
    submitted = []
    monkeypatch.setattr(
        "apps.recommendations.tasks.index_product_vectors.apply_async",
        lambda **kwargs: submitted.append(kwargs),
    )

    result = sync_stale_products_to_qdrant(batch_size=3, max_products=7)

    assert result == {"submitted": 7, "batches": 3, "status": "scheduled"}
    assert [len(call["kwargs"]["product_ids"]) for call in submitted] == [3, 3, 1]
    assert all(call["priority"] == 3 for call in submitted)
