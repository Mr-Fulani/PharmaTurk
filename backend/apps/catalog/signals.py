"""Сигналы для каскадного удаления медиа-файлов из хранилища (R2/локальное) и автоскачивания из URL."""
import logging

from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from .models import (
    BannerMedia,
    BookVariantImage,
    Brand,
    Category,
    MarketingBrand,
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


def delete_file_from_storage(file_field, storage=None):
    """Удалить файл из хранилища (R2 или локальный диск), если поле заполнено."""
    if not file_field or not hasattr(file_field, "name") or not file_field.name:
        return
    path = file_field.name
    if not path or not path.strip():
        return
    try:
        from django.core.files.storage import default_storage

        backend = storage if storage is not None else default_storage
        if backend.exists(path):
            backend.delete(path)
            logger.info("Deleted old file from storage: %s", path)
        else:
            logger.warning("File not found in storage (already deleted?): %s", path)
    except Exception as e:
        logger.warning("Failed to delete file %s: %s", path, e)


def delete_url_from_storage(url):
    if not url:
        return
    try:
        from urllib.parse import urlparse
        from django.core.files.storage import default_storage

        parsed = urlparse(url)
        path = parsed.path or ""
        if not path:
            return
        if not (path.startswith("/products/") or path.startswith("/media/")):
            return
        storage_path = path.lstrip("/")
        if default_storage.exists(storage_path):
            default_storage.delete(storage_path)
    except Exception as e:
        logger.warning("Failed to delete file by url %s: %s", url, e)


def is_internal_storage_url(url):
    if not url:
        return False
    try:
        from urllib.parse import urlparse
        from django.conf import settings

        r2_public = getattr(settings, "R2_PUBLIC_URL", "")
        r2_bucket = getattr(settings, "R2_BUCKET_NAME", "")
        if r2_public and url.startswith(r2_public):
            return True
        if r2_bucket and (f"{r2_bucket}.r2.dev" in url or "r2.cloudflarestorage.com" in url):
            return True
        parsed = urlparse(url)
        if parsed.path.startswith("/media/") or parsed.path.startswith("/products/"):
            return True
        return False
    except Exception:
        return False


# --- Product ---


@receiver(post_delete, sender=Product)
def delete_product_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)
    delete_file_from_storage(instance.main_video_file)
    delete_url_from_storage(instance.main_image)
    delete_url_from_storage(instance.video_url)


@receiver(post_delete, sender=ProductImage)
def delete_product_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)
    delete_file_from_storage(instance.video_file)
    delete_url_from_storage(instance.image_url)
    delete_url_from_storage(instance.video_url)


# --- Category, Brand ---


@receiver(pre_save, sender=Category)
def delete_old_category_card_media(sender, instance, **kwargs):
    """Удаляет старый файл card_media из облака при замене на новый или при переключении на external_url."""
    if not instance.pk:
        return
    try:
        old = Category.objects.get(pk=instance.pk)
        if not old.card_media or not old.card_media.name:
            return
        old_path = old.card_media.name

        new_file = instance.card_media
        new_path = None
        if new_file and hasattr(new_file, "name") and new_file.name:
            new_path = new_file.name

        if old_path == new_path:
            return

        field = Category._meta.get_field("card_media")
        storage = field.storage
        delete_file_from_storage(old.card_media, storage=storage)
    except Category.DoesNotExist:
        pass
    except Exception as e:
        logger.warning("Failed to delete old Category.card_media: %s", e)


def _delete_old_brand_card_media_impl(instance):
    """Удаляет старый файл card_media из облака при замене на новый или при переключении на external_url."""
    if not instance.pk:
        return
    try:
        old = Brand.objects.get(pk=instance.pk)
        if not old.card_media or not old.card_media.name:
            return
        old_path = old.card_media.name

        # Новое значение: файл или пусто (при очистке / переключении на external_url)
        new_file = instance.card_media
        new_path = None
        if new_file and hasattr(new_file, "name") and new_file.name:
            new_path = new_file.name

        if old_path == new_path:
            return

        field = Brand._meta.get_field("card_media")
        storage = field.storage
        delete_file_from_storage(old.card_media, storage=storage)
    except Brand.DoesNotExist:
        pass
    except Exception as e:
        logger.warning("Failed to delete old Brand.card_media: %s", e)


@receiver(pre_save, sender=Brand)
def delete_old_brand_card_media(sender, instance, **kwargs):
    _delete_old_brand_card_media_impl(instance)


@receiver(pre_save, sender=MarketingBrand)
def delete_old_marketing_brand_card_media(sender, instance, **kwargs):
    """MarketingBrand — proxy модели Brand; при сохранении через админку «Маркетинг» pre_save Brand не срабатывает."""
    _delete_old_brand_card_media_impl(instance)


@receiver(post_delete, sender=Category)
def delete_category_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.card_media)


@receiver(post_delete, sender=Brand)
def delete_brand_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.card_media)


@receiver(post_delete, sender=MarketingBrand)
def delete_marketing_brand_files(sender, instance, **kwargs):
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
    delete_file_from_storage(instance.main_video_file)


@receiver(post_delete, sender=ShoeProductImage)
def delete_shoe_product_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)


@receiver(post_delete, sender=ShoeVariant)
def delete_shoe_variant_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)


@receiver(post_delete, sender=ShoeVariantImage)
def delete_shoe_variant_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)


# --- Electronics ---


@receiver(post_delete, sender=ElectronicsProduct)
def delete_electronics_product_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)
    delete_file_from_storage(instance.main_video_file)


@receiver(post_delete, sender=ElectronicsProductImage)
def delete_electronics_product_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)


# --- Furniture ---


@receiver(post_delete, sender=FurnitureProduct)
def delete_furniture_product_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)
    delete_file_from_storage(instance.main_video_file)


@receiver(post_delete, sender=FurnitureVariant)
def delete_furniture_variant_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)


@receiver(post_delete, sender=FurnitureVariantImage)
def delete_furniture_variant_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)


# --- Jewelry ---


@receiver(post_delete, sender=JewelryProduct)
def delete_jewelry_product_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)
    delete_file_from_storage(instance.main_video_file)


@receiver(post_delete, sender=JewelryProductImage)
def delete_jewelry_product_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)


@receiver(post_delete, sender=JewelryVariant)
def delete_jewelry_variant_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)


@receiver(post_delete, sender=JewelryVariantImage)
def delete_jewelry_variant_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)


# --- Books ---


@receiver(post_delete, sender=BookVariantImage)
def delete_book_variant_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)


# --- Banner ---


@receiver(post_delete, sender=BannerMedia)
def delete_banner_media_files(sender, instance, **kwargs):
    if instance.image:
        delete_file_from_storage(instance.image)
    if instance.video_file:
        delete_file_from_storage(instance.video_file)
    if instance.gif_file:
        delete_file_from_storage(instance.gif_file)


# --- Auto-download signals ---


def _download_url_to_file(url):
    """Скачать файл по URL и вернуть ContentFile (или None)."""
    import requests
    from django.core.files.base import ContentFile
    from urllib.parse import urlparse
    import os

    try:
        response = requests.get(url, stream=True, timeout=10)
        if response.status_code == 200:
            filename = os.path.basename(urlparse(url).path)
            if not filename:
                filename = "image.jpg"
            return ContentFile(response.content, name=filename)
    except Exception as e:
        logger.warning(f"Failed to download image from {url}: {e}")
    return None


def _save_downloaded_file_to_storage(instance, file_attr, file_obj):
    """
    Присвоить полю скачанный файл. Django сам сохранит его в storage при model.save().
    НЕ вызываем storage.save() здесь — иначе при file_overwrite=False создаётся дубликат
    (сигнал сохраняет, потом Django сохраняет ещё раз с суффиксом).
    """
    import os
    import uuid
    from django.core.files.base import ContentFile

    field = instance._meta.get_field(file_attr)
    upload_to = getattr(field, "upload_to", None)
    ext = os.path.splitext(getattr(file_obj, "name", "image.jpg") or "image.jpg")[1] or ".jpg"
    # Уникальное имя — один save через Django, без дубликатов
    basename = f"{uuid.uuid4().hex[:12]}{ext}"
    content = file_obj.read() if hasattr(file_obj, "read") else file_obj
    setattr(instance, file_attr, ContentFile(content, name=basename))


@receiver(pre_save, sender=Product)
def auto_set_product_type_from_category(sender, instance, **kwargs):
    """
    Автоматически выставляет product_type на основе категории,
    если он стоит по умолчанию ('medicines') или не задан.
    """
    if not instance.category:
        return

    # Если тип уже задан и не равен дефолтному 'medicines', не трогаем
    # (предполагаем, что 'medicines' - это дефолт, который мы хотим уточнить,
    # если категория явно говорит о другом)
    if instance.product_type and instance.product_type != 'medicines':
        return

    # Если категория сама по себе "medicines", то менять ничего не надо
    if instance.category.slug == 'medicines':
        return

    # 1. Пробуем взять из CategoryType
    if instance.category.category_type:
        type_slug = instance.category.category_type.slug
        # Проверяем, есть ли такой тип в PRODUCT_TYPE_CHOICES
        valid_types = dict(Product.PRODUCT_TYPE_CHOICES).keys()
        if type_slug in valid_types:
            instance.product_type = type_slug
            return

    # 2. Пробуем определить по слагу категории (или родителей)
    valid_types = dict(Product.PRODUCT_TYPE_CHOICES).keys()
    
    current = instance.category
    while current:
        slug = current.slug.lower()
        # Проверяем точное совпадение
        if slug in valid_types:
            instance.product_type = slug
            return
            
        # Проверяем частичное совпадение (префикс/суффикс)
        for vt in valid_types:
            if slug == vt or slug.startswith(f"{vt}-") or f"-{vt}" in slug:
                instance.product_type = vt
                return
        
        current = current.parent


@receiver(pre_save, sender=Product)
def auto_download_product_media_from_url(sender, instance, **kwargs):
    """Автоматически скачивать медиа из URL полей в файловые поля Product (через default_storage → R2)."""
    external_data = instance.external_data if isinstance(instance.external_data, dict) else {}
    source = external_data.get("source")
    if source and source != "api":
        return

    # Удалить старые файлы из R2 при замене на URL или очистке
    if instance.pk:
        try:
            old = Product.objects.only("main_image_file", "main_video_file").get(pk=instance.pk)
            if old.main_image_file and old.main_image_file.name:
                if not (instance.main_image_file and instance.main_image_file.name):
                    delete_file_from_storage(old.main_image_file)
                    logger.info("Deleted old main_image_file from R2 for Product %s", instance.pk)
            if old.main_video_file and old.main_video_file.name:
                if not (instance.main_video_file and instance.main_video_file.name):
                    delete_file_from_storage(old.main_video_file)
                    logger.info("Deleted old main_video_file from R2 for Product %s", instance.pk)
        except Product.DoesNotExist:
            pass

    if instance.main_image and not instance.main_image_file:
        if not is_internal_storage_url(instance.main_image):
            file_obj = _download_url_to_file(instance.main_image)
            if file_obj:
                _save_downloaded_file_to_storage(instance, "main_image_file", file_obj)
                logger.info("Auto-downloaded main_image URL to main_image_file for Product %s", instance.id or "new")

    if instance.video_url and external_data.get("source") and not is_internal_storage_url(instance.video_url):
        return

    if instance.video_url and not instance.main_video_file and not is_internal_storage_url(instance.video_url):
        file_obj = _download_url_to_file(instance.video_url)
        if file_obj:
            _save_downloaded_file_to_storage(instance, "main_video_file", file_obj)
            logger.info("Auto-downloaded video_url to main_video_file for Product %s", instance.id or "new")


@receiver(pre_save, sender=JewelryProduct)
def auto_download_jewelry_product_media_from_url(sender, instance, **kwargs):
    """Автоматически скачивать медиа из URL в файлы JewelryProduct (Reels из Instagram и т.д.)."""
    # Удалить старые файлы из R2 при замене на URL или при очистке полей
    if instance.pk:
        try:
            old = JewelryProduct.objects.only("main_image_file", "main_video_file").get(pk=instance.pk)
            if old.main_image_file and old.main_image_file.name:
                new_empty = not (instance.main_image_file and instance.main_image_file.name)
                if new_empty:
                    delete_file_from_storage(old.main_image_file)
                    logger.info("Deleted old main_image_file from R2 for JewelryProduct %s: %s", instance.pk, old.main_image_file.name)
            if old.main_video_file and old.main_video_file.name:
                new_empty = not (instance.main_video_file and instance.main_video_file.name)
                if new_empty:
                    delete_file_from_storage(old.main_video_file)
                    logger.info("Deleted old main_video_file from R2 for JewelryProduct %s", instance.pk)
        except JewelryProduct.DoesNotExist:
            pass

    if instance.main_image and not instance.main_image_file:
        if not is_internal_storage_url(instance.main_image):
            file_obj = _download_url_to_file(instance.main_image)
            if file_obj:
                _save_downloaded_file_to_storage(instance, "main_image_file", file_obj)
                logger.info("Auto-downloaded main_image URL to main_image_file for JewelryProduct %s", instance.id or "new")

    if instance.video_url and not instance.main_video_file:
        if not is_internal_storage_url(instance.video_url):
            file_obj = _download_url_to_file(instance.video_url)
            if file_obj:
                _save_downloaded_file_to_storage(instance, "main_video_file", file_obj)
                logger.info("Auto-downloaded video_url to main_video_file for JewelryProduct %s", instance.id or "new")


@receiver(pre_save, sender=ClothingProduct)
def auto_download_clothing_product_media_from_url(sender, instance, **kwargs):
    """Автоматически скачивать медиа из URL полей в файловые поля ClothingProduct (через default_storage → R2)."""
    if instance.pk:
        try:
            old = ClothingProduct.objects.only("main_image_file", "main_video_file").get(pk=instance.pk)
            if old.main_image_file and old.main_image_file.name:
                if not (instance.main_image_file and instance.main_image_file.name):
                    delete_file_from_storage(old.main_image_file)
                    logger.info("Deleted old main_image_file from R2 for ClothingProduct %s", instance.pk)
            if old.main_video_file and old.main_video_file.name:
                if not (instance.main_video_file and instance.main_video_file.name):
                    delete_file_from_storage(old.main_video_file)
                    logger.info("Deleted old main_video_file from R2 for ClothingProduct %s", instance.pk)
        except ClothingProduct.DoesNotExist:
            pass

    if instance.main_image and not instance.main_image_file:
        if not is_internal_storage_url(instance.main_image):
            file_obj = _download_url_to_file(instance.main_image)
            if file_obj:
                _save_downloaded_file_to_storage(instance, "main_image_file", file_obj)
                logger.info("Auto-downloaded main_image URL to main_image_file for ClothingProduct %s", instance.id or "new")

    if instance.video_url and not instance.main_video_file:
        if not is_internal_storage_url(instance.video_url):
            file_obj = _download_url_to_file(instance.video_url)
            if file_obj:
                _save_downloaded_file_to_storage(instance, "main_video_file", file_obj)
                logger.info("Auto-downloaded video_url to main_video_file for ClothingProduct %s", instance.id or "new")


def _auto_download_image_url_to_file(instance, url_attr="image_url", file_attr="image_file", log_label=""):
    """Общая логика: скачать по URL и записать в file-поле (через default_storage), если URL внешний и file пустой."""
    url = getattr(instance, url_attr, None)
    file_field = getattr(instance, file_attr, None)
    if not url or (file_field and file_field.name):
        return

    if not is_internal_storage_url(url):
        file_obj = _download_url_to_file(url)
        if file_obj:
            _save_downloaded_file_to_storage(instance, file_attr, file_obj)
            logger.info(f"{log_label} {instance.id or 'new'}")
