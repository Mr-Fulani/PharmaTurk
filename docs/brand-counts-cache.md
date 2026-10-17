# Brand display counters

The brand list uses a shared Django cache snapshot for global `products_count`.
Celery Beat schedules `catalog.refresh_brand_product_counts` every 60 seconds.
It uses the same public Product visibility rules as before: active, available,
excluding source variants and medicine stubs. Metadata, media and homepage
priorities are read live. Brand detail/product endpoints retain exact database
counts.

The same refresh stores a per-product-type snapshot
(`catalog:brand-type-product-counts:v1`, `{product_type: {brand_id: total}}`) from
one grouped query; the global counts are its sum. `count_scope=filtered` with a
`product_type` and no category filter (the root category page sidebar) reads it.
The exact query had to detoast `external_data` of every product of the type —
medicine brands took ~7 s on production, and PostgreSQL ignores the partial
brand index because it underestimates the detoast cost. Filtered requests with
`category_id`/`category_slug` still count exactly.

Normal count freshness is approximately one minute plus calculation/queue time.
The last successful snapshot expires after 15 minutes; failed calculations do
not replace it. An empty snapshot is valid. On a cold cache or cache outage the
request computes exact counts, so ranking is never based on placeholder zeroes.
This fallback can be slow. Check worker/Beat health if slow requests recur.

Before switching to a new backend, warm only these cache keys from the new image,
with production Django settings and the normal Redis cache connection:

```python
from apps.catalog.brand_counts import refresh_brand_product_counts
counts = refresh_brand_product_counts()
print({"brands": len(counts), "products": sum(counts.values())})
```

Use the supported backend-only release workflow. No migration or catalogue
rewrite is required. The frontend contract is unchanged. Rollback to the previous
backend ignores the new cache keys, which expire automatically. Never clear the
shared cache to warm or diagnose this feature.
