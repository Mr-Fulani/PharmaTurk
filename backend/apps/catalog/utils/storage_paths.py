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


def _category_chain(category) -> str:
    """Иерархия слагов категории root/.../leaf (через parent). '' если категории нет."""
    out = []
    cur = category
    seen = set()
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        s = _normalize_slug(getattr(cur, "slug", None), "")
        if s:
            out.append(s)
        cur = getattr(cur, "parent", None)
    return "/".join(reversed(out))


def _brand_slug(product) -> str:
    """Слаг бренда товара для имени файла ('' если бренда нет)."""
    if product is None:
        return ""
    brand = getattr(product, "brand", None)
    name = getattr(brand, "name", None) if brand else None
    return _normalize_slug(name, "")


def _build_readable_filename(parts: list[str], filename: str, fallback: str = "media") -> str:
    ext = os.path.splitext(str(filename).split("?")[0])[1].lower() or ".jpg"
    # slugify(None) у Django даёт "none" — поэтому пустые части отсекаем ДО slugify,
    # иначе в имя попадает мусорное "none" (badge/slug/цвет, которых нет).
    # Часть может быть иерархией "root/.../leaf" — в имя берём последний сегмент (leaf).
    parts = [str(p).rsplit("/", 1)[-1] if p else p for p in parts]
    base = "-".join(part for part in (slugify(p or "").strip("-") for p in parts) if part)
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
    """Product.main_image_file → одна папка товара."""
    return f"{_product_dir(instance)}/{_product_media_name(instance, filename, role='main')}"


def get_product_image_upload_path(instance, filename):
    """ProductImage.image_file → одна папка товара."""
    product = getattr(instance, "product", None)
    return f"{_product_dir(product)}/{_product_media_name(product, filename, role='gallery')}"


def _domain_type_slug(product) -> str:
    """Путь типа доменного товара: иерархия категории root/.../leaf → product_type → other."""
    if product is None:
        return "other"
    chain = _category_chain(getattr(product, "category", None))
    if chain:
        return chain.lower()
    pt = getattr(product, "product_type", None) or getattr(product, "_domain_product_type", None) or ""
    return (str(pt).replace("_", "-") or "other").lower()


def _parser_slug(product) -> str:
    """Слаг парсера-сайта из external_id ('flo-100320223' → 'flo'). '' если нет."""
    if product is None:
        return ""
    ext = str(getattr(product, "external_id", "") or "")
    if not ext:
        bp = getattr(product, "base_product", None)
        ext = str(getattr(bp, "external_id", "") or "") if bp else ""
    if "-" in ext:
        prefix = ext.split("-", 1)[0].strip().lower()
        if prefix and not prefix.isdigit():
            return _normalize_slug(prefix, "")
    return ""


def _product_dir(product) -> str:
    """Единая папка товара: products/{категория-или-тип}/{slug-товара}/."""
    cat = _domain_type_slug(product)
    slug = _normalize_slug(getattr(product, "slug", None), "product")
    return f"products/{cat}/{slug}"


def _product_media_name(product, filename, *, color=None, role="gallery") -> str:
    """Имя файла: {парсер}-{бренд}-{цвет}-{роль}-{hash}.{ext}."""
    return _build_readable_filename(
        [_parser_slug(product), _brand_slug(product), color, role],
        filename,
        role,
    )


def get_domain_main_upload_path(instance, filename):
    """*Product.main_image_file → одна папка товара."""
    return f"{_product_dir(instance)}/{_product_media_name(instance, filename, role='main')}"


def get_domain_variant_main_upload_path(instance, filename):
    """*Variant.main_image_file → одна папка товара (имя с цветом)."""
    product = getattr(instance, "product", None)
    color = getattr(instance, "color", None) or getattr(instance, "name", None)
    return f"{_product_dir(product)}/{_product_media_name(product, filename, color=color, role='main')}"


def get_domain_gallery_upload_path(instance, filename):
    """*ProductImage.image_file → одна папка товара."""
    product = getattr(instance, "product", None)
    return f"{_product_dir(product)}/{_product_media_name(product, filename, role='gallery')}"


def get_domain_variant_gallery_upload_path(instance, filename):
    """*VariantImage.image_file → одна папка товара (имя с цветом)."""
    variant = getattr(instance, "variant", None)
    product = getattr(variant, "product", None) if variant else None
    color = getattr(variant, "color", None) if variant else None
    return f"{_product_dir(product)}/{_product_media_name(product, filename, color=color, role='gallery')}"


def get_book_product_gallery_upload_path(instance, filename):
    """Галерея книги → одна папка товара."""
    product = getattr(instance, "product", None)
    ref = getattr(product, "base_product", None) if product else None
    ref = ref or product
    return f"{_product_dir(ref)}/{_product_media_name(ref, filename, role='gallery')}"


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


def get_service_upload_path(instance, filename):
    """Service.main_image_file/main_video_file → services/{слаг-услуги}/main/{images|videos}/{читаемое}.

    Группируем по самой услуге (а не по её категории) — чтобы всё медиа одной
    услуги лежало в одной папке и легко отслеживалось.
    """
    service_slug = _normalize_slug(getattr(instance, "slug", None), "service")
    media_folder = _media_folder_from_filename(filename)
    readable_name = _build_readable_filename([service_slug, "main"], filename, "service-main")
    return f"services/{service_slug}/main/{media_folder}/{readable_name}"


def get_service_image_upload_path(instance, filename):
    """ServiceImage.image_file/video_file → services/{слаг-услуги}/gallery/{images|videos}/{читаемое}."""
    service = getattr(instance, "service", None)
    service_slug = _normalize_slug(getattr(service, "slug", None) if service else None, "service")
    media_folder = _media_folder_from_filename(filename)
    readable_name = _build_readable_filename([service_slug, "gallery"], filename, "service-gallery")
    return f"services/{service_slug}/gallery/{media_folder}/{readable_name}"


def get_service_portfolio_media_upload_path(instance, filename):
    """ServicePortfolioMedia.media_file → services/{слаг-услуги}/portfolio/{images|videos}/{читаемое}.

    Группируем по самой услуге — всё медиа услуги (main/gallery/portfolio) в одной папке.
    Если кейс заведён без услуги (под категорией) — fallback на слаг категории/кейса.
    """
    item = getattr(instance, "portfolio_item", None)
    service = getattr(item, "service", None) if item else None
    base_slug = _normalize_slug(getattr(service, "slug", None) if service else None, "")
    if not base_slug:
        category = getattr(item, "category", None) if item else None
        base_slug = (
            _normalize_slug(getattr(category, "slug", None), "")
            or _normalize_slug(getattr(item, "title", None) if item else None, "")
            or "other"
        )
    media_folder = _media_folder_from_filename(filename)
    badge = getattr(instance, "badge", None)
    badge = badge if badge and badge != "none" else None
    readable_name = _build_readable_filename([base_slug, badge, "portfolio"], filename, "portfolio")
    return f"services/{base_slug}/portfolio/{media_folder}/{readable_name}"


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


JEWELRY_TYPE_TO_SLUG = {
    "ring": "rings",
    "bracelet": "bracelets",
    "necklace": "necklaces",
    "earrings": "earrings",
    "pendant": "pendants",
}


def _jewelry_type_slug(instance) -> str:
    """Slug типа украшения (rings, bracelets и т.д.) или slug категории."""
    product = getattr(instance, "product", None)
    if product:
        return _jewelry_type_slug(product)
    variant = getattr(instance, "variant", None)
    if variant and getattr(variant, "product", None):
        return _jewelry_type_slug(variant.product)
    jewelry_type = getattr(instance, "jewelry_type", None) or ""
    slug = JEWELRY_TYPE_TO_SLUG.get(jewelry_type) or _normalize_slug(jewelry_type, "")
    if slug:
        return slug
    category = getattr(instance, "category", None)
    cat_slug = _normalize_slug(getattr(category, "slug", None), "")
    return cat_slug or "other"


def get_jewelry_main_upload_path(instance, filename):
    """Украшение main → одна папка товара."""
    return f"{_product_dir(instance)}/{_product_media_name(instance, filename, role='main')}"


def get_jewelry_gallery_upload_path(instance, filename):
    """Украшение gallery → одна папка товара."""
    product = getattr(instance, "product", None)
    return f"{_product_dir(product)}/{_product_media_name(product, filename, role='gallery')}"


def get_jewelry_variant_upload_path(instance, filename):
    """Украшение variant main → одна папка товара."""
    product = getattr(instance, "product", None)
    color = getattr(instance, "color", None) or getattr(instance, "name", None)
    return f"{_product_dir(product)}/{_product_media_name(product, filename, color=color, role='main')}"


def get_jewelry_variant_gallery_upload_path(instance, filename):
    """Украшение variant gallery → одна папка товара."""
    variant = getattr(instance, "variant", None)
    product = getattr(variant, "product", None) if variant else None
    color = getattr(variant, "color", None) if variant else None
    return f"{_product_dir(product)}/{_product_media_name(product, filename, color=color, role='gallery')}"


def get_parsed_media_upload_path(parser_name, media_type, filename, sub_folder=None):
    """
    Динамический upload_to для медиа из парсеров.

    Args:
        parser_name: Имя парсера (instagram, ilacabak, zara и т.д.)
        media_type: Тип медиа ('image', 'video', 'gif')
        filename: Имя файла
        sub_folder: Опциональная подпапка для группировки (имя аккаунта или категория)

    Returns:
        str: Путь в формате products/parsed/{parser_name}/[{sub_folder}/]{media_type}s/{filename}
    """
    parser_slug = parser_name.lower().replace(" ", "-").replace("_", "-")

    media_folder = {
        "image": "images",
        "video": "videos",
        "gif": "gifs",
    }.get(media_type, "images")

    if sub_folder:
        sub_slug = _normalize_slug(sub_folder, "")
        if sub_slug:
            return f"products/parsed/{parser_slug}/{sub_slug}/{media_folder}/{filename}"

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
