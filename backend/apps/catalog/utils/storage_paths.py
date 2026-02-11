"""Динамические пути загрузки медиа для R2/локального хранилища.

Поддержка разделения по типам товаров (медицина, БАДы, медтехника и т.д.)
и по парсерам (instagram, ilacabak, zara и т.д.) с подпапками images/videos/gifs.
"""
import os
import uuid
from django.utils.text import slugify


def _normalize_slug(value: str | None, fallback: str) -> str:
    slug = slugify(value or "").strip("-")
    return slug or fallback


def _build_readable_filename(parts: list[str], filename: str, fallback: str = "media") -> str:
    ext = os.path.splitext(str(filename).split("?")[0])[1].lower() or ".jpg"
    base = "-".join(part for part in (slugify(p).strip("-") for p in parts) if part)
    base = (base or fallback).strip("-")[:160]
    suffix = uuid.uuid4().hex[:10]
    return f"{base}-{suffix}{ext}"


def _media_folder_from_filename(filename: str) -> str:
    media_type = detect_media_type(filename)
    return {
        "image": "images",
        "video": "videos",
        "gif": "gifs",
    }.get(media_type, "images")


def get_product_upload_path(instance, filename):
    """Динамический upload_to для Product.main_image_file на основе product_type."""
    product_type = (getattr(instance, "product_type", None) or "").replace("_", "-")
    category_slug = _normalize_slug(getattr(getattr(instance, "category", None), "slug", None), "")
    base = (category_slug or product_type or "other").lower()
    media_folder = _media_folder_from_filename(filename)
    readable_name = _build_readable_filename(
        [category_slug or product_type, getattr(instance, "slug", None), getattr(instance, "name", None)],
        filename,
        "product-main",
    )
    return f"products/{base}/main/{media_folder}/{readable_name}"


def get_product_image_upload_path(instance, filename):
    """Динамический upload_to для ProductImage.image_file."""
    product = getattr(instance, "product", None)
    product_type = (getattr(product, "product_type", None) or "").replace("_", "-")
    category_slug = _normalize_slug(getattr(getattr(product, "category", None), "slug", None), "")
    base = (category_slug or product_type or "other").lower()
    media_folder = _media_folder_from_filename(filename)
    readable_name = _build_readable_filename(
        [category_slug or product_type, getattr(product, "slug", None), getattr(product, "name", None), "gallery"],
        filename,
        "product-gallery",
    )
    return f"products/{base}/gallery/{media_folder}/{readable_name}"


def get_category_card_upload_path(instance, filename):
    """
    Динамический upload_to для Category.card_media.
    Папка берётся из category_type.slug или category.slug — без хардкода,
    чтобы новые типы категорий автоматически получали свою папку.
    """
    category_slug = _normalize_slug(getattr(instance, "slug", None), "")
    category_type = getattr(instance, "category_type", None)
    type_slug = _normalize_slug(getattr(category_type, "slug", None), "")
    media_folder = _media_folder_from_filename(filename)

    # Приоритет: тип категории → slug категории → slug родителя → "other"
    base = type_slug or category_slug
    if not base and getattr(instance, "parent", None):
        parent = instance.parent
        base = _normalize_slug(getattr(parent, "slug", None), "") or _normalize_slug(
            getattr(getattr(parent, "category_type", None), "slug", None), ""
        )
    base = (base or "other").lower()

    readable_name = _build_readable_filename([category_slug or base, "card"], filename, "category-card")
    return f"marketing/cards/categories/{base}/{media_folder}/{readable_name}"


def get_brand_card_upload_path(instance, filename):
    brand_slug = _normalize_slug(getattr(instance, "slug", None), "brand")
    media_folder = _media_folder_from_filename(filename)
    readable_name = _build_readable_filename([brand_slug, "card"], filename, "brand-card")
    return f"marketing/cards/brands/{media_folder}/{readable_name}"


def get_banner_image_upload_path(instance, filename):
    banner = getattr(instance, "banner", None)
    position = _normalize_slug(getattr(banner, "position", None), "banner")
    title = getattr(banner, "title", None)
    readable_name = _build_readable_filename([position, title, "image"], filename, "banner-image")
    return f"marketing/banners/{position}/images/{readable_name}"


def get_banner_video_upload_path(instance, filename):
    banner = getattr(instance, "banner", None)
    position = _normalize_slug(getattr(banner, "position", None), "banner")
    title = getattr(banner, "title", None)
    readable_name = _build_readable_filename([position, title, "video"], filename, "banner-video")
    return f"marketing/banners/{position}/videos/{readable_name}"


def get_banner_gif_upload_path(instance, filename):
    banner = getattr(instance, "banner", None)
    position = _normalize_slug(getattr(banner, "position", None), "banner")
    title = getattr(banner, "title", None)
    readable_name = _build_readable_filename([position, title, "gif"], filename, "banner-gif")
    return f"marketing/banners/{position}/gifs/{readable_name}"


def get_parsed_media_upload_path(parser_name, media_type, filename):
    """
    Динамический upload_to для медиа из парсеров.

    Args:
        parser_name: Имя парсера (instagram, ilacabak, zara и т.д.)
        media_type: Тип медиа ('image', 'video', 'gif')
        filename: Имя файла

    Returns:
        str: Путь в формате products/parsed/{parser_name}/{media_type}s/{filename}
    """
    parser_slug = parser_name.lower().replace(" ", "-").replace("_", "-")

    media_folder = {
        "image": "images",
        "video": "videos",
        "gif": "gifs",
    }.get(media_type, "images")

    return f"products/parsed/{parser_slug}/{media_folder}/{filename}"


def detect_media_type(file_url_or_path):
    """
    Определить тип медиа по расширению файла.

    Args:
        file_url_or_path: URL или путь к файлу

    Returns:
        str: 'image', 'video' или 'gif'
    """
    ext = os.path.splitext(str(file_url_or_path).lower().split("?")[0])[1]

    image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}
    video_extensions = {".mp4", ".mov", ".avi", ".webm", ".mkv", ".flv"}
    gif_extensions = {".gif"}

    if ext in gif_extensions:
        return "gif"
    if ext in video_extensions:
        return "video"
    if ext in image_extensions:
        return "image"
    return "image"
