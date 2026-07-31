"""Pure helpers for keeping list-card API payloads small and stable."""

CARD_PRODUCT_FIELDS = (
    'id', 'base_product_id', 'name', 'slug', 'description', 'product_type',
    'price', 'price_formatted', 'old_price', 'old_price_formatted',
    'active_variant_price', 'active_variant_currency',
    'active_variant_old_price_formatted', 'currency',
    'main_image', 'main_image_url', 'images', 'video_url',
    'main_video_url', 'main_gif_url', 'has_manual_main_image',
    'is_available', 'is_featured', 'is_new', 'created_at',
    'publication_date', 'translations', 'rating', 'reviews_count',
    'brand_id',
    'isbn', 'publisher', 'pages', 'language', 'book_authors',
    'is_bestseller',
)

CARD_IMAGE_FIELDS = (
    'id', 'image_url', 'alt_text', 'sort_order', 'is_main',
    # ProductCard uses these to render variant swatches and their links.
    'variant_slug', 'color',
)


def compact_card_product_payload(row):
    """Remove detail-only fields while preserving everything ProductCard uses."""
    if not isinstance(row, dict):
        return row

    compact = {
        field: row[field]
        for field in CARD_PRODUCT_FIELDS
        if field in row and row[field] is not None
    }
    description = compact.get('description')
    if isinstance(description, str):
        compact['description'] = description[:240]

    # В карточке достаточно внешнего ключа: название берётся из уже загруженного
    # списка брендов сайдбара. Это не дублирует тяжёлый BrandSerializer в каждом товаре.
    brand = row.get('brand')
    brand_id = row.get('brand_id')
    if brand_id is None and isinstance(brand, dict):
        brand_id = brand.get('id')
    if brand_id is not None:
        compact['brand_id'] = brand_id

    images = compact.get('images')
    if isinstance(images, list):
        compact['images'] = [
            {
                field: image[field]
                for field in CARD_IMAGE_FIELDS
                if isinstance(image, dict)
                and field in image
                and image[field] is not None
            }
            for image in images
            if isinstance(image, dict)
        ]

    translations = compact.get('translations')
    if isinstance(translations, list):
        compact['translations'] = [
            {
                field: (
                    translation[field][:240]
                    if field == 'description'
                    and isinstance(translation.get(field), str)
                    else translation[field]
                )
                for field in ('locale', 'name', 'description')
                if isinstance(translation, dict)
                and field in translation
                and translation[field] is not None
            }
            for translation in translations
            if isinstance(translation, dict)
        ]

    authors = compact.get('book_authors')
    if isinstance(authors, list):
        compact['book_authors'] = [
            {
                **(
                    {'id': author['id']}
                    if author.get('id') is not None
                    else {}
                ),
                **(
                    {
                        'author': {
                            field: author['author'][field]
                            for field in ('id', 'full_name', 'full_name_en')
                            if author['author'].get(field) is not None
                        }
                    }
                    if isinstance(author.get('author'), dict)
                    else {}
                ),
            }
            for author in authors
            if isinstance(author, dict)
        ]
    return compact
