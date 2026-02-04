"""Сигналы для каскадного удаления медиа-файлов из хранилища (R2/локальное) и автоскачивания из URL."""
import logging

from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from .models import (
    BannerMedia,
    BookVariantImage,
    Brand,
    Category,
    ClothingProduct,
    ClothingProductImage,
    ClothingVariant,
    ClothingVariantImage,
    ElectronicsProduct,
    ElectronicsProductImage,
    FurnitureProduct,
    FurnitureVariant,
    FurnitureVariantImage,
    JewelryProduct,
    JewelryProductImage,
    JewelryVariant,
    JewelryVariantImage,
    Product,
    ProductImage,
    ShoeProduct,
    ShoeProductImage,
    ShoeVariant,
    ShoeVariantImage,
)

logger = logging.getLogger(__name__)


def delete_file_from_storage(file_field):
    """Удалить файл из default_storage (R2 или локальный диск), если поле заполнено."""
    if file_field and hasattr(file_field, "name") and file_field.name:
        try:
            from django.core.files.storage import default_storage

            default_storage.delete(file_field.name)
        except Exception as e:
            logger.warning("Failed to delete file %s: %s", getattr(file_field, "name", ""), e)


# --- Product ---


@receiver(post_delete, sender=Product)
def delete_product_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)
    delete_file_from_storage(instance.main_video_file)


@receiver(post_delete, sender=ProductImage)
def delete_product_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)
    delete_file_from_storage(instance.video_file)


# --- Category, Brand ---


@receiver(post_delete, sender=Category)
def delete_category_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.card_media)


@receiver(post_delete, sender=Brand)
def delete_brand_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.card_media)


# --- Clothing ---


@receiver(post_delete, sender=ClothingProduct)
def delete_clothing_product_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)
    delete_file_from_storage(instance.main_video_file)


@receiver(post_delete, sender=ClothingProductImage)
def delete_clothing_product_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)


@receiver(post_delete, sender=ClothingVariant)
def delete_clothing_variant_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)


@receiver(post_delete, sender=ClothingVariantImage)
def delete_clothing_variant_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)


# --- Shoes ---


@receiver(post_delete, sender=ShoeProduct)
def delete_shoe_product_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)


@receiver(post_delete, sender=ShoeProductImage)
def delete_shoe_product_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)


@receiver(post_delete, sender=ShoeVariant)
def delete_shoe_variant_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)


@receiver(post_delete, sender=ShoeVariantImage)
def delete_shoe_variant_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)


# --- Jewelry ---


@receiver(post_delete, sender=JewelryProduct)
def delete_jewelry_product_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)


@receiver(post_delete, sender=JewelryProductImage)
def delete_jewelry_product_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)


@receiver(post_delete, sender=JewelryVariant)
def delete_jewelry_variant_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)


@receiver(post_delete, sender=JewelryVariantImage)
def delete_jewelry_variant_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)


# --- Electronics ---


@receiver(post_delete, sender=ElectronicsProduct)
def delete_electronics_product_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)


@receiver(post_delete, sender=ElectronicsProductImage)
def delete_electronics_product_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)


# --- Furniture ---


@receiver(post_delete, sender=FurnitureProduct)
def delete_furniture_product_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)


@receiver(post_delete, sender=FurnitureVariant)
def delete_furniture_variant_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)


@receiver(post_delete, sender=FurnitureVariantImage)
def delete_furniture_variant_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)


# --- Books ---


@receiver(post_delete, sender=BookVariantImage)
def delete_book_variant_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)


# --- Banners ---


@receiver(post_delete, sender=BannerMedia)
def delete_banner_media_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image)
    delete_file_from_storage(instance.video_file)
    delete_file_from_storage(instance.gif_file)


# --- Автоскачивание URL → R2 ---


def _get_download_headers(url):
    """Заголовки для скачивания (Pinterest, Instagram и др. требуют Referer/User-Agent)."""
    url_lower = (url or "").lower()
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    if "instagram" in url_lower or "fbcdn.net" in url_lower or "cdninstagram" in url_lower:
        return {"User-Agent": ua, "Referer": "https://www.instagram.com/"}
    if "pinterest" in url_lower or "pinimg.com" in url_lower:
        return {"User-Agent": ua, "Referer": "https://www.pinterest.com/"}
    # Для остальных ссылок — браузерный User-Agent, иначе многие CDN отдают 403
    return {"User-Agent": ua}


def _download_url_to_file(url):
    """Скачать медиа из URL и вернуть file-like объект (ContentFile)."""
    if not url or not url.startswith(("http://", "https://")):
        return None
    try:
        import httpx
        from django.core.files.base import ContentFile
        from apps.catalog.utils.storage_paths import detect_media_type
        from apps.catalog.utils.image_optimizer import ImageOptimizer
        from io import BytesIO
        import os

        headers = _get_download_headers(url)
        media_type = detect_media_type(url)
        timeout = 30 if media_type in ("video", "gif") else 15

        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            content = response.content

        ext = os.path.splitext(url.split("?")[0].lower())[1] or ".jpg"

        if media_type == "image":
            try:
                optimizer = ImageOptimizer()
                file_obj = optimizer.optimize_image(BytesIO(content))
                return file_obj
            except Exception:
                pass

        filename = f"downloaded{ext}"
        return ContentFile(content, name=filename)

    except Exception as e:
        logger.warning("Failed to download URL %s: %s", url[:80], e)
        return None


@receiver(pre_save, sender=Product)
def auto_download_product_media_from_url(sender, instance, **kwargs):
    """Автоматически скачивать медиа из URL полей в файловые поля Product (через default_storage → R2)."""
    from django.conf import settings
    r2_public = getattr(settings, "R2_PUBLIC_URL", "")

    if instance.main_image and not instance.main_image_file:
        if not (instance.main_image.startswith("/media/") or (r2_public and instance.main_image.startswith(r2_public))):
            file_obj = _download_url_to_file(instance.main_image)
            if file_obj:
                _save_downloaded_file_to_storage(instance, "main_image_file", file_obj)
                logger.info("Auto-downloaded main_image URL to main_image_file for Product %s", instance.id or "new")

    if instance.video_url and not instance.main_video_file:
        if not (instance.video_url.startswith("/media/") or (r2_public and instance.video_url.startswith(r2_public))):
            file_obj = _download_url_to_file(instance.video_url)
            if file_obj:
                _save_downloaded_file_to_storage(instance, "main_video_file", file_obj)
                logger.info("Auto-downloaded video_url to main_video_file for Product %s", instance.id or "new")


@receiver(pre_save, sender=ClothingProduct)
def auto_download_clothing_product_media_from_url(sender, instance, **kwargs):
    """Автоматически скачивать медиа из URL полей в файловые поля ClothingProduct (через default_storage → R2)."""
    from django.conf import settings
    r2_public = getattr(settings, "R2_PUBLIC_URL", "")

    if instance.main_image and not instance.main_image_file:
        if not (instance.main_image.startswith("/media/") or (r2_public and instance.main_image.startswith(r2_public))):
            file_obj = _download_url_to_file(instance.main_image)
            if file_obj:
                _save_downloaded_file_to_storage(instance, "main_image_file", file_obj)
                logger.info("Auto-downloaded main_image URL to main_image_file for ClothingProduct %s", instance.id or "new")

    if instance.video_url and not instance.main_video_file:
        if not (instance.video_url.startswith("/media/") or (r2_public and instance.video_url.startswith(r2_public))):
            file_obj = _download_url_to_file(instance.video_url)
            if file_obj:
                _save_downloaded_file_to_storage(instance, "main_video_file", file_obj)
                logger.info("Auto-downloaded video_url to main_video_file for ClothingProduct %s", instance.id or "new")


def _save_downloaded_file_to_storage(instance, file_attr, file_obj):
    """
    Сохранить файл в то же хранилище, что и у поля (field.storage → R2 или локальный диск),
    и присвоить полю сохранённое имя. Использование field.storage гарантирует, что файл
    попадёт в R2, если у модели настроен R2, а не в локальный media.
    В поле передаём только basename, иначе Django делает os.path.join(upload_to, filename)
    и путь дублируется (products/clothing/gallery/products/clothing/gallery/xxx.jpg).
    """
    import os
    import uuid
    from django.core.files.base import ContentFile

    field = instance._meta.get_field(file_attr)
    storage = field.storage  # тот же бэкенд, что и при сохранении формы (R2 или local)
    upload_to = getattr(field, "upload_to", None)
    if callable(upload_to):
        try:
            path = upload_to(instance, getattr(file_obj, "name", "image.jpg") or "image.jpg")
        except Exception:
            path = f"products/gallery/{uuid.uuid4().hex[:12]}.jpg"
    else:
        base = (upload_to or "products/gallery/").rstrip("/")
        path = f"{base}/{uuid.uuid4().hex[:12]}.jpg"
    saved_name = storage.save(path, file_obj)
    with storage.open(saved_name, "rb") as f:
        content = f.read()
    # Только basename, иначе FileField при save() дублирует upload_to в пути
    setattr(instance, file_attr, ContentFile(content, name=os.path.basename(saved_name)))


def _auto_download_image_url_to_file(instance, url_attr="image_url", file_attr="image_file", log_label=""):
    """Общая логика: скачать по URL и записать в file-поле (через default_storage), если URL внешний и file пустой."""
    from django.conf import settings
    r2_public = getattr(settings, "R2_PUBLIC_URL", "")
    url = getattr(instance, url_attr, None)
    file_field = getattr(instance, file_attr, None)
    if not url or (file_field and file_field.name):
        return
    if url.startswith("/media/") or (r2_public and url.startswith(r2_public)):
        return
    file_obj = _download_url_to_file(url)
    if file_obj:
        _save_downloaded_file_to_storage(instance, file_attr, file_obj)
        logger.info("Auto-downloaded %s to %s for %s %s", url_attr, file_attr, log_label, instance.id or "new")


@receiver(pre_save, sender=ProductImage)
def auto_download_product_image_from_url(sender, instance, **kwargs):
    """Автоматически скачивать медиа из URL полей в файловые поля ProductImage."""
    _auto_download_image_url_to_file(instance, "image_url", "image_file", "ProductImage")
    if hasattr(instance, "video_url") and instance.video_url and not getattr(instance, "video_file", None):
        _auto_download_image_url_to_file(instance, "video_url", "video_file", "ProductImage")


@receiver(pre_save, sender=ClothingProductImage)
def auto_download_clothing_product_image_from_url(sender, instance, **kwargs):
    """Автоматически скачивать изображение из image_url в image_file для ClothingProductImage."""
    _auto_download_image_url_to_file(instance, "image_url", "image_file", "ClothingProductImage")


@receiver(pre_save, sender=ClothingVariantImage)
def auto_download_clothing_variant_image_from_url(sender, instance, **kwargs):
    _auto_download_image_url_to_file(instance, "image_url", "image_file", "ClothingVariantImage")


@receiver(pre_save, sender=ShoeProductImage)
def auto_download_shoe_product_image_from_url(sender, instance, **kwargs):
    _auto_download_image_url_to_file(instance, "image_url", "image_file", "ShoeProductImage")


@receiver(pre_save, sender=ShoeVariantImage)
def auto_download_shoe_variant_image_from_url(sender, instance, **kwargs):
    _auto_download_image_url_to_file(instance, "image_url", "image_file", "ShoeVariantImage")


@receiver(pre_save, sender=JewelryProductImage)
def auto_download_jewelry_product_image_from_url(sender, instance, **kwargs):
    _auto_download_image_url_to_file(instance, "image_url", "image_file", "JewelryProductImage")


@receiver(pre_save, sender=JewelryVariantImage)
def auto_download_jewelry_variant_image_from_url(sender, instance, **kwargs):
    _auto_download_image_url_to_file(instance, "image_url", "image_file", "JewelryVariantImage")


@receiver(pre_save, sender=ElectronicsProductImage)
def auto_download_electronics_product_image_from_url(sender, instance, **kwargs):
    _auto_download_image_url_to_file(instance, "image_url", "image_file", "ElectronicsProductImage")


@receiver(pre_save, sender=FurnitureVariantImage)
def auto_download_furniture_variant_image_from_url(sender, instance, **kwargs):
    _auto_download_image_url_to_file(instance, "image_url", "image_file", "FurnitureVariantImage")


@receiver(pre_save, sender=BookVariantImage)
def auto_download_book_variant_image_from_url(sender, instance, **kwargs):
    _auto_download_image_url_to_file(instance, "image_url", "image_file", "BookVariantImage")
