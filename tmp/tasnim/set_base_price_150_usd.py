import json
from decimal import Decimal

from django.db import transaction

from apps.catalog.currency_models import ProductPrice
from apps.catalog.models import Brand, Category, IslamicClothingProduct, Product


BASE_PRICE = Decimal("150.00")
BASE_CURRENCY = "USD"
TARGET_CURRENCIES = ["RUB", "USD", "KZT", "EUR", "TRY", "USDT"]


with transaction.atomic():
    brand = Brand.objects.select_for_update().get(slug="tasnim")
    category = Category.objects.select_for_update().get(
        slug="burkini",
        parent__slug="islamic-clothing",
    )

    domain_products = IslamicClothingProduct.objects.select_for_update().filter(
        category=category,
        brand=brand,
    )
    base_products = Product.objects.select_for_update().filter(
        category=category,
        brand=brand,
    )

    domain_count = domain_products.count()
    base_count = base_products.count()
    if domain_count != 85 or base_count != 85:
        raise RuntimeError(
            f"Expected 85 domain and 85 base products, got {domain_count} and {base_count}"
        )

    domain_updated = domain_products.exclude(
        price=BASE_PRICE,
        currency=BASE_CURRENCY,
    ).update(price=BASE_PRICE, currency=BASE_CURRENCY)
    base_updated = base_products.exclude(
        price=BASE_PRICE,
        currency=BASE_CURRENCY,
    ).update(price=BASE_PRICE, currency=BASE_CURRENCY)

    conversion_attempts = 0
    for product in base_products.iterator(chunk_size=100):
        product.update_currency_prices(TARGET_CURRENCIES)
        conversion_attempts += 1

    price_info = ProductPrice.objects.select_for_update().filter(product__in=base_products)
    invalid_price_info = price_info.exclude(
        base_price=BASE_PRICE,
        base_currency=BASE_CURRENCY,
    ).count()
    if price_info.count() != base_count or invalid_price_info:
        raise RuntimeError(
            "Price conversion records are incomplete: "
            f"count={price_info.count()}, invalid={invalid_price_info}"
        )

    snapshots = [
        Product(
            pk=row.product_id,
            converted_price_rub=row.rub_price,
            converted_price_usd=row.usd_price,
            final_price_rub=row.rub_price_with_margin,
            final_price_usd=row.usd_price_with_margin,
        )
        for row in price_info.only(
            "product_id",
            "rub_price",
            "usd_price",
            "rub_price_with_margin",
            "usd_price_with_margin",
        )
    ]
    Product.objects.bulk_update(
        snapshots,
        [
            "converted_price_rub",
            "converted_price_usd",
            "final_price_rub",
            "final_price_usd",
        ],
        batch_size=100,
    )

    final_domain_count = domain_products.filter(
        price=BASE_PRICE,
        currency=BASE_CURRENCY,
    ).count()
    final_base_count = base_products.filter(
        price=BASE_PRICE,
        currency=BASE_CURRENCY,
    ).count()
    final_price_info_count = price_info.filter(
        base_price=BASE_PRICE,
        base_currency=BASE_CURRENCY,
    ).count()
    if (
        final_domain_count != domain_count
        or final_base_count != base_count
        or final_price_info_count != base_count
    ):
        raise RuntimeError("Final price verification failed")

    result = {
        "brand_id": brand.id,
        "category_id": category.id,
        "base_price": str(BASE_PRICE),
        "base_currency": BASE_CURRENCY,
        "domain_products_updated": domain_updated,
        "base_products_updated": base_updated,
        "conversion_attempts": conversion_attempts,
        "final_domain_products": final_domain_count,
        "final_base_products": final_base_count,
        "final_product_price_records": final_price_info_count,
        "converted_price_samples": list(
            price_info.order_by("product_id").values(
                "product_id",
                "base_price",
                "base_currency",
                "rub_price",
                "rub_price_with_margin",
                "usd_price",
                "usd_price_with_margin",
            )[:3]
        ),
    }

print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
