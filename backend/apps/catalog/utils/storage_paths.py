"""Динамические пути загрузки медиа для R2/локального хранилища.

Поддержка разделения по типам товаров (медицина, БАДы, медтехника и т.д.)
и по парсерам (instagram, ilacabak, zara и т.д.) с подпапками images/videos/gifs.
"""
import os


def get_product_upload_path(instance, filename):
    """Динамический upload_to для Product.main_image_file на основе product_type."""
    product_type = getattr(instance, "product_type", None) or ""

    # Медицинские категории (приоритет)
    if product_type == "medicines":
        return f"products/medicines/main/{filename}"
    if product_type == "supplements":
        return f"products/supplements/main/{filename}"
    if product_type == "medical_equipment":
        return f"products/medical-equipment/main/{filename}"

    # Остальные категории
    if product_type == "clothing":
        return f"products/clothing/main/{filename}"
    if product_type == "shoes":
        return f"products/shoes/main/{filename}"
    if product_type == "jewelry":
        return f"products/jewelry/main/{filename}"
    if product_type == "electronics":
        return f"products/electronics/main/{filename}"
    if product_type == "furniture":
        return f"products/furniture/main/{filename}"
    if product_type == "books":
        return f"products/books/main/{filename}"
    if product_type == "tableware":
        return f"products/tableware/main/{filename}"
    if product_type == "accessories":
        return f"products/accessories/main/{filename}"
    if product_type == "underwear":
        return f"products/underwear/main/{filename}"
    if product_type == "headwear":
        return f"products/headwear/main/{filename}"

    return f"products/main/{filename}"


def get_product_image_upload_path(instance, filename):
    """Динамический upload_to для ProductImage.image_file."""
    product = getattr(instance, "product", None)
    product_type = getattr(product, "product_type", None) if product else None

    if product_type == "medicines":
        return f"products/medicines/gallery/{filename}"
    if product_type == "supplements":
        return f"products/supplements/gallery/{filename}"
    if product_type == "medical_equipment":
        return f"products/medical-equipment/gallery/{filename}"
    if product_type == "clothing":
        return f"products/clothing/gallery/{filename}"
    if product_type == "shoes":
        return f"products/shoes/gallery/{filename}"
    if product_type == "jewelry":
        return f"products/jewelry/gallery/{filename}"
    if product_type == "electronics":
        return f"products/electronics/gallery/{filename}"
    if product_type == "furniture":
        return f"products/furniture/gallery/{filename}"
    if product_type == "books":
        return f"products/books/gallery/{filename}"
    if product_type == "tableware":
        return f"products/tableware/gallery/{filename}"
    if product_type == "accessories":
        return f"products/accessories/gallery/{filename}"
    if product_type == "underwear":
        return f"products/underwear/gallery/{filename}"
    if product_type == "headwear":
        return f"products/headwear/gallery/{filename}"

    return f"products/gallery/{filename}"


def get_category_card_upload_path(instance, filename):
    """Динамический upload_to для Category.card_media."""
    category_slug = (getattr(instance, "slug", None) or "").lower()
    category_type = getattr(instance, "category_type", None)
    type_slug = getattr(category_type, "slug", "").lower() if category_type else ""

    if "medic" in type_slug or "medic" in category_slug or type_slug == "medicines":
        return f"marketing/cards/categories/medicines/{filename}"
    if "supplement" in type_slug or "supplement" in category_slug or "bad" in category_slug:
        return f"marketing/cards/categories/supplements/{filename}"
    if "equipment" in type_slug or "equipment" in category_slug or "medical-equipment" in type_slug:
        return f"marketing/cards/categories/medical-equipment/{filename}"
    if type_slug == "clothing" or "clothing" in category_slug:
        return f"marketing/cards/categories/clothing/{filename}"
    if type_slug == "shoes" or "shoes" in category_slug:
        return f"marketing/cards/categories/shoes/{filename}"
    if type_slug == "jewelry" or "jewelry" in category_slug:
        return f"marketing/cards/categories/jewelry/{filename}"
    if type_slug == "electronics" or "electronics" in category_slug:
        return f"marketing/cards/categories/electronics/{filename}"
    if type_slug == "furniture" or "furniture" in category_slug:
        return f"marketing/cards/categories/furniture/{filename}"

    return f"marketing/cards/categories/{filename}"


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
