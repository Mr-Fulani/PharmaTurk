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
    """Заголовки для скачивания (Instagram CDN и др. требуют Referer/User-Agent)."""
    url_lower = (url or "").lower()
    if "instagram" in url_lower or "fbcdn.net" in url_lower or "cdninstagram" in url_lower:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.instagram.com/",
        }
    return {}


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
    """Автоматически скачивать медиа из URL полей в файловые поля Product."""
    from django.conf import settings
    r2_public = getattr(settings, "R2_PUBLIC_URL", "")
    
    if instance.main_image and not instance.main_image_file:
        if not (instance.main_image.startswith("/media/") or (r2_public and instance.main_image.startswith(r2_public))):
            file_obj = _download_url_to_file(instance.main_image)
            if file_obj:
                instance.main_image_file = file_obj
                logger.info("Auto-downloaded main_image URL to main_image_file for Product %s", instance.id or "new")

    if instance.video_url and not instance.main_video_file:
        if not (instance.video_url.startswith("/media/") or (r2_public and instance.video_url.startswith(r2_public))):
            file_obj = _download_url_to_file(instance.video_url)
            if file_obj:
                instance.main_video_file = file_obj
                logger.info("Auto-downloaded video_url to main_video_file for Product %s", instance.id or "new")


@receiver(pre_save, sender=ClothingProduct)
def auto_download_clothing_product_media_from_url(sender, instance, **kwargs):
    """Автоматически скачивать медиа из URL полей в файловые поля ClothingProduct."""
    from django.conf import settings
    r2_public = getattr(settings, "R2_PUBLIC_URL", "")

    if instance.main_image and not instance.main_image_file:
        if not (instance.main_image.startswith("/media/") or (r2_public and instance.main_image.startswith(r2_public))):
            file_obj = _download_url_to_file(instance.main_image)
            if file_obj:
                instance.main_image_file = file_obj
                logger.info("Auto-downloaded main_image URL to main_image_file for ClothingProduct %s", instance.id or "new")

    if instance.video_url and not instance.main_video_file:
        if not (instance.video_url.startswith("/media/") or (r2_public and instance.video_url.startswith(r2_public))):
            file_obj = _download_url_to_file(instance.video_url)
            if file_obj:
                instance.main_video_file = file_obj
                logger.info("Auto-downloaded video_url to main_video_file for ClothingProduct %s", instance.id or "new")


@receiver(pre_save, sender=ProductImage)
def auto_download_product_image_from_url(sender, instance, **kwargs):
    """Автоматически скачивать медиа из URL полей в файловые поля ProductImage."""
    from django.conf import settings
    r2_public = getattr(settings, "R2_PUBLIC_URL", "")
    
    if instance.image_url and not instance.image_file:
        if not (instance.image_url.startswith("/media/") or (r2_public and instance.image_url.startswith(r2_public))):
            file_obj = _download_url_to_file(instance.image_url)
            if file_obj:
                instance.image_file = file_obj
                logger.info("Auto-downloaded image_url to image_file for ProductImage %s", instance.id or "new")

    if hasattr(instance, "video_url") and instance.video_url and not instance.video_file:
        if not (instance.video_url.startswith("/media/") or (r2_public and instance.video_url.startswith(r2_public))):
            file_obj = _download_url_to_file(instance.video_url)
            if file_obj:
                instance.video_file = file_obj
                logger.info("Auto-downloaded video_url to video_file for ProductImage %s", instance.id or "new")
