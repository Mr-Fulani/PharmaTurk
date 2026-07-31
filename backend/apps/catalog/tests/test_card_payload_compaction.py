def test_card_payload_keeps_variant_media_and_drops_detail_fields():
    from apps.catalog.card_payload import compact_card_product_payload

    payload = {
        "id": 7,
        "base_product_id": 70,
        "name": "Variant product",
        "slug": "variant-product",
        "description": "x" * 500,
        "price": "1200.00",
        "currency": "RUB",
        "brand": {
            "id": 9,
            "name": "Card Brand",
            "slug": "card-brand",
            "description": "detail only",
            "translations": [{"locale": "ru", "name": "Бренд"}],
        },
        "images": [
            {
                "id": 11,
                "image_url": "/media/card.jpg",
                "variant_slug": "variant-blue",
                "color": "Blue",
                "video_url": "/media/detail-only.mp4",
            }
        ],
        "translations": [
            {
                "locale": "ru",
                "name": "Вариативный товар",
                "description": "д" * 500,
                "seo_title": "detail only",
            }
        ],
        "book_authors": [
            {
                "id": 4,
                "author": {
                    "id": 8,
                    "full_name": "Иван Автор",
                    "full_name_en": "Ivan Author",
                    "bio": "detail only",
                },
                "created_at": "2026-07-31T00:00:00Z",
            }
        ],
        "variants": [{"id": 3, "stock_quantity": 10}],
        "dynamic_attributes": [{"slug": "material", "value": "cotton"}],
        "meta_title": "Detail SEO",
    }

    compact = compact_card_product_payload(payload)

    assert compact["base_product_id"] == 70
    assert compact["brand_id"] == 9
    assert "brand" not in compact
    assert compact["images"] == [
        {
            "id": 11,
            "image_url": "/media/card.jpg",
            "variant_slug": "variant-blue",
            "color": "Blue",
        }
    ]
    assert len(compact["description"]) == 240
    assert len(compact["translations"][0]["description"]) == 240
    assert compact["book_authors"] == [
        {
            "id": 4,
            "author": {
                "id": 8,
                "full_name": "Иван Автор",
                "full_name_en": "Ivan Author",
            },
        }
    ]
    assert "variants" not in compact
    assert "dynamic_attributes" not in compact
    assert "meta_title" not in compact
