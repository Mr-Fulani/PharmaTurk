"""Сигналы для каскадного удаления медиа-файлов из хранилища (R2/локальное) и автоскачивания из URL."""
import logging

from django.core.exceptions import ObjectDoesNotExist
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver

from .models import (
    BannerMedia,
    AccessoryProduct,
    AccessoryProductImage,
    AutoPartProduct,
    AutoPartProductImage,
    BookProduct,
    BookProductImage,
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
    HeadwearProduct,
    HeadwearProductImage,
    HeadwearVariant,
    HeadwearVariantImage,
    IncenseProduct,
    IncenseProductImage,
    IslamicClothingProduct,
    IslamicClothingProductImage,
    IslamicClothingVariant,
    IslamicClothingVariantImage,
    JewelryProduct,
    JewelryProductImage,
    JewelryVariant,
    JewelryVariantImage,
    MedicalEquipmentProduct,
    MedicalEquipmentProductImage,
    MedicineProduct,
    MedicineProductImage,
    PerfumeryProduct,
    PerfumeryProductImage,
    PerfumeryVariant,
    PerfumeryVariantImage,
    Product,
    ProductImage,
    Service,
    ServiceImage,
    ShoeProduct,
    ShoeProductImage,
    ShoeVariant,
    ShoeVariantImage,
    SportsProduct,
    SportsProductImage,
    SupplementProduct,
    SupplementProductImage,
    TablewareProduct,
    TablewareProductImage,
    UnderwearProduct,
    UnderwearProductImage,
    UnderwearVariant,
    UnderwearVariantImage,
)

logger = logging.getLogger(__name__)

# Имена reverse OneToOne с Product на доменные модели (base_product → related_name="*_item").
_PRODUCT_DOMAIN_ONE_TO_ONE_RELS = (
    "clothing_item",
    "shoe_item",
    "jewelry_item",
    "electronics_item",
    "furniture_item",
    "book_item",
    "perfumery_item",
    "medicine_item",
    "supplement_item",
    "medical_equipment_item",
    "tableware_item",
    "accessory_item",
    "incense_item",
    "sports_item",
    "auto_part_item",
    "headwear_item",
    "underwear_item",
    "islamic_clothing_item",
)


def _get_or_create_other_brand():
    """Возвращает бренд «Другое», создаёт при отсутствии."""
    other_brand = Brand.objects.filter(slug="other").first()
    if other_brand:
        return other_brand
    return Brand.objects.create(
        name="Другое",
        slug="other",
        is_active=True,
    )


@receiver(pre_save, sender=Product)
@receiver(pre_save, sender=ClothingProduct)
@receiver(pre_save, sender=ShoeProduct)
@receiver(pre_save, sender=JewelryProduct)
@receiver(pre_save, sender=ElectronicsProduct)
@receiver(pre_save, sender=FurnitureProduct)
@receiver(pre_save, sender=BookProduct)
@receiver(pre_save, sender=PerfumeryProduct)
@receiver(pre_save, sender=MedicineProduct)
@receiver(pre_save, sender=SupplementProduct)
@receiver(pre_save, sender=MedicalEquipmentProduct)
@receiver(pre_save, sender=TablewareProduct)
@receiver(pre_save, sender=AccessoryProduct)
@receiver(pre_save, sender=IncenseProduct)
@receiver(pre_save, sender=SportsProduct)
@receiver(pre_save, sender=AutoPartProduct)
@receiver(pre_save, sender=HeadwearProduct)
@receiver(pre_save, sender=UnderwearProduct)
@receiver(pre_save, sender=IslamicClothingProduct)
def set_default_other_brand(sender, instance, **kwargs):
    """
    Для всех категорий товаров: если бренд не указан, подставляем бренд «Другое».
    """
    if getattr(instance, "brand_id", None):
        return
    try:
        instance.brand = _get_or_create_other_brand()
    except Exception as e:
        logger.warning("Не удалось подставить бренд 'Другое' для %s: %s", sender.__name__, e)


@receiver(pre_delete, sender=Product)
def delete_domain_before_generic_product(sender, instance, **kwargs):
    """При удалении Product сначала удалить доменную карточку (варианты и пр. — каскадом с неё)."""
    for attr in _PRODUCT_DOMAIN_ONE_TO_ONE_RELS:
        try:
            related = getattr(instance, attr)
        except ObjectDoesNotExist:
            continue
        if related is not None:
            related.delete(skip_shadow_delete=True)


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
    """
    Удаление внутреннего файла по URL из R2/локального storage.
    Файл удаляется только если после удаления записи на него больше не осталось ссылок в БД.
    """
    path = _get_path_from_storage_url(url)
    if not path:
        return
    normalized_path = _normalize_storage_key_for_file_field(path)
    if not normalized_path:
        return
    try:
        from django.core.files.storage import default_storage
        from .tasks import _collect_db_media_paths, _normalize_media_path

        db_paths = _collect_db_media_paths()
        if _normalize_media_path(normalized_path) in db_paths:
            logger.info("Skip deleting shared internal URL from storage: %s", normalized_path)
            return
        if default_storage.exists(normalized_path):
            default_storage.delete(normalized_path)
            logger.info("Deleted internal URL from storage: %s", normalized_path)
        else:
            logger.warning("Internal URL path not found in storage (already deleted?): %s", normalized_path)
    except Exception as e:
        logger.warning("Failed to delete internal URL %s: %s", normalized_path, e)


def _get_path_from_storage_url(url: str) -> str | None:
    """Извлечь путь к файлу из URL хранилища (с учетом префикса)."""
    if not url:
        return None
    try:
        from urllib.parse import urlparse
        from django.conf import settings
        from .utils.r2_utils import get_r2_path

        r2_public = (getattr(settings, "R2_CONFIG", {}).get("public_url", "") or "").rstrip("/")
        
        # Если URL начинается с публичного R2 URL
        if r2_public and url.startswith(r2_public):
            path = url[len(r2_public):].lstrip("/")
            return path
            
        parsed = urlparse(url)
        path = parsed.path or ""
        if path.startswith("/media/"):
            return path[len("/media/"):].lstrip("/")
        if path.startswith("/products/"):
             return path.lstrip("/")
        return None
    except Exception:
        return None


def _normalize_storage_key_for_file_field(path: str) -> str:
    """Нормализует ключ для FileField (без дублирования R2_PREFIX/location)."""
    if not path:
        return path
    normalized = path.lstrip("/")
    if normalized.startswith("media/"):
        normalized = normalized[len("media/") :]
    try:
        from django.conf import settings

        r2_prefix = (getattr(settings, "R2_PREFIX", "") or "").strip("/")
        if r2_prefix and normalized.startswith(f"{r2_prefix}/"):
            normalized = normalized[len(r2_prefix) + 1 :]
    except Exception:
        # В pre_save лучше не прерывать сохранение товара из-за ошибки нормализации.
        pass
    return normalized


def is_internal_storage_url(url):
    if not url:
        return False
    try:
        from django.conf import settings
        
        r2_config = getattr(settings, "R2_CONFIG", {})
        r2_public = r2_config.get("public_url", "")
        r2_bucket = r2_config.get("bucket_name", "")
        
        if r2_public and url.startswith(r2_public):
            return True
        if r2_bucket and (f"{r2_bucket}.r2.dev" in url or "r2.cloudflarestorage.com" in url):
            return True
            
        from urllib.parse import urlparse
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


@receiver(post_delete, sender=Service)
def delete_service_files(sender, instance, **kwargs):
    """Удалить файлы услуги из хранилища при удалении из БД."""
    delete_file_from_storage(instance.main_image_file)
    delete_file_from_storage(instance.main_video_file)
    delete_file_from_storage(instance.gif_file)
    delete_url_from_storage(instance.main_image)
    delete_url_from_storage(instance.video_url)


@receiver(post_delete, sender=ServiceImage)
def delete_service_image_files(sender, instance, **kwargs):
    """Удалить файлы из галереи услуги при удалении из БД."""
    delete_file_from_storage(instance.image_file)
    delete_url_from_storage(instance.image_url)


@receiver(pre_save, sender=ProductImage)
def auto_download_product_image_from_url(sender, instance, **kwargs):
    """Автоматически скачивать изображения из URL в файлы ProductImage."""
    if instance.image_url and not instance.image_file:
        if not is_internal_storage_url(instance.image_url):
            file_obj = _download_url_to_file(instance.image_url)
            if file_obj:
                _save_downloaded_file_to_storage(instance, "image_file", file_obj)
                logger.info("Auto-downloaded ProductImage URL to image_file for Product %s", instance.product_id)


def _auto_download_impl(instance, field_name="image_file", url_field="image_url"):
    """Реализация автоскачивания для любой модели."""
    url = getattr(instance, url_field, None)
    file_val = getattr(instance, field_name, None)
    if url and not file_val:
        if not is_internal_storage_url(url):
            file_obj = _download_url_to_file(url)
            if file_obj:
                _save_downloaded_file_to_storage(instance, field_name, file_obj)
                logger.info(f"Auto-downloaded {instance.__class__.__name__} URL to {field_name}")
        else:
            # Если URL внутренний (например, cdn.mudaroba.com), пробуем извлечь путь
            try:
                from urllib.parse import urlparse
                path = _normalize_storage_key_for_file_field(urlparse(url).path)
                # Простая проверка: если путь не пустой, сохраняем как файл
                if path:
                    setattr(instance, field_name, path)
                    # Обычно сохранять модель здесь не нужно, так как это pre_save сигнал,
                    # но изменения поля будут сохранены при сохранении инстанса.
                    logger.info(f"Set {field_name} from internal URL: {path}")
            except Exception as e:
                logger.warning(f"Failed to set internal path for {instance.__class__.__name__}: {e}")


@receiver(pre_save, sender=ClothingProductImage)
@receiver(pre_save, sender=ClothingVariantImage)
@receiver(pre_save, sender=ElectronicsProductImage)
@receiver(pre_save, sender=FurnitureVariantImage)
@receiver(pre_save, sender=JewelryProductImage)
@receiver(pre_save, sender=JewelryVariantImage)
@receiver(pre_save, sender=ShoeProductImage)
@receiver(pre_save, sender=ShoeVariantImage)
def auto_download_domain_image_from_url(sender, instance, **kwargs):
    """Автоматически скачивать изображения для доменных моделей."""
    _auto_download_impl(instance)


@receiver(pre_save, sender=ServiceImage)
def auto_download_service_image_gallery(sender, instance, **kwargs):
    """Автоматически скачивать изображения для галереи услуг."""
    _auto_download_impl(instance, "image_file", "image_url")


# --- Category, Brand ---


@receiver(pre_save, sender=Category)
def delete_old_category_card_media(sender, instance, **kwargs):
    """Удаляет старый файл card_media из облака при замене на новый или при переключении на external_url."""
    if not instance.pk:
        # Новая запись: пробуем сразу скачать external_url → card_media
        if instance.card_media_external_url and not (instance.card_media and instance.card_media.name):
            if not is_internal_storage_url(instance.card_media_external_url):
                file_obj = _download_url_to_file(instance.card_media_external_url)
                if file_obj:
                    _save_downloaded_file_to_storage(instance, "card_media", file_obj)
                    instance.card_media_external_url = ""  # переключаемся на локальный файл
                    logger.info("Auto-downloaded new Category.card_media from %s", instance.card_media_external_url)
        return
    try:
        old = Category.objects.get(pk=instance.pk)

        # Авто-скачивание: если external_url заполнен и файла нет — скачиваем
        if instance.card_media_external_url and not (instance.card_media and instance.card_media.name):
            if not is_internal_storage_url(instance.card_media_external_url):
                file_obj = _download_url_to_file(instance.card_media_external_url)
                if file_obj:
                    _save_downloaded_file_to_storage(instance, "card_media", file_obj)
                    instance.card_media_external_url = ""  # переключаемся на локальный файл
                    logger.info("Auto-downloaded Category.card_media (pk=%s)", instance.pk)

        # Удаление старого файла при замене
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
        # Новая запись: пробуем сразу скачать external_url → card_media
        if instance.card_media_external_url and not (instance.card_media and instance.card_media.name):
            if not is_internal_storage_url(instance.card_media_external_url):
                file_obj = _download_url_to_file(instance.card_media_external_url)
                if file_obj:
                    _save_downloaded_file_to_storage(instance, "card_media", file_obj)
                    instance.card_media_external_url = ""
                    logger.info("Auto-downloaded new Brand.card_media")
        return
    try:
        old = Brand.objects.get(pk=instance.pk)

        # Авто-скачивание: если external_url заполнен и файла нет — скачиваем
        if instance.card_media_external_url and not (instance.card_media and instance.card_media.name):
            if not is_internal_storage_url(instance.card_media_external_url):
                file_obj = _download_url_to_file(instance.card_media_external_url)
                if file_obj:
                    _save_downloaded_file_to_storage(instance, "card_media", file_obj)
                    instance.card_media_external_url = ""  # переключаемся на локальный файл
                    logger.info("Auto-downloaded Brand.card_media (pk=%s)", instance.pk)

        # Удаление старого файла при замене
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



@receiver(post_delete, sender=ShoeProductImage)
def delete_shoe_product_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)


@receiver(post_delete, sender=ShoeVariant)
def delete_shoe_variant_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)


@receiver(post_delete, sender=ShoeVariantImage)
def delete_shoe_variant_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)


# --- Services Signal handlers for media and prices ---

@receiver(post_save, sender=Service)
def sync_service_price_info(sender, instance, created, **kwargs):
    """Синхронизировать цену услуги с ServicePrice (конвертация + маржа)."""
    if instance.price and instance.price > 0:
        from .utils.currency_converter import currency_converter
        currency_converter.update_or_create_service_price(
            service_instance=instance,
            base_price=instance.price,
            base_currency=instance.currency or "RUB"
        )


@receiver(pre_save, sender=Service)
def auto_download_service_media(sender, instance, **kwargs):
    """Автоматически скачивать медиа из URL полей в файлы Service."""
    # Удалить старые файлы при замене
    if instance.pk:
        try:
            old = Service.objects.only("main_image", "main_image_file", "main_video_file", "gif_file").get(pk=instance.pk)
            
            # Если URL изображения изменился, удаляем старый файл
            if old.main_image_file and old.main_image_file.name:
                url_changed = (instance.main_image != old.main_image)
                is_empty = not (instance.main_image_file and instance.main_image_file.name)
                if url_changed and is_empty:
                    delete_file_from_storage(old.main_image_file)
            
            # Если URL видео изменился
            if old.main_video_file and old.main_video_file.name:
                v_url_changed = (instance.video_url != old.video_url)
                v_is_empty = not (instance.main_video_file and instance.main_video_file.name)
                if v_url_changed and v_is_empty:
                    delete_file_from_storage(old.main_video_file)
        except Service.DoesNotExist:
            pass

    # Автоскачивание
    if instance.main_image and not instance.main_image_file:
        _auto_download_impl(instance, "main_image_file", "main_image")
        
    if instance.video_url and not instance.main_video_file:
        _auto_download_impl(instance, "main_video_file", "video_url")


# --- Electronics ---


@receiver(post_delete, sender=ElectronicsProduct)
def delete_electronics_product_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)
    if hasattr(instance, "main_video_file"):
        delete_file_from_storage(instance.main_video_file)


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


@receiver(post_delete, sender=BookProductImage)
def delete_book_product_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)
    delete_file_from_storage(instance.video_file)
    delete_url_from_storage(instance.image_url)
    delete_url_from_storage(instance.video_url)


@receiver(pre_save, sender=BookProductImage)
def auto_download_book_product_image(sender, instance, **kwargs):
    _auto_download_image_url_to_file(
        instance, url_attr="image_url", file_attr="image_file",
        log_label="Auto-downloaded BookProductImage",
    )


@receiver(post_delete, sender=BookVariantImage)
def delete_book_variant_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)


@receiver(pre_save, sender=BookVariantImage)
def auto_download_book_variant_image(sender, instance, **kwargs):
    _auto_download_image_url_to_file(
        instance, url_attr="image_url", file_attr="image_file",
        log_label="Auto-downloaded BookVariantImage",
    )


# --- Tableware ---


@receiver(pre_save, sender=TablewareProductImage)
def auto_download_tableware_product_image(sender, instance, **kwargs):
    _auto_download_image_url_to_file(
        instance, url_attr="image_url", file_attr="image_file",
        log_label="Auto-downloaded TablewareProductImage",
    )


@receiver(post_delete, sender=TablewareProductImage)
def delete_tableware_product_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)
    delete_url_from_storage(instance.image_url)


# --- Accessories ---


@receiver(pre_save, sender=AccessoryProductImage)
def auto_download_accessory_product_image(sender, instance, **kwargs):
    _auto_download_image_url_to_file(
        instance, url_attr="image_url", file_attr="image_file",
        log_label="Auto-downloaded AccessoryProductImage",
    )


@receiver(post_delete, sender=AccessoryProductImage)
def delete_accessory_product_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)
    delete_url_from_storage(instance.image_url)


# --- Incense ---


@receiver(pre_save, sender=IncenseProductImage)
def auto_download_incense_product_image(sender, instance, **kwargs):
    _auto_download_image_url_to_file(
        instance, url_attr="image_url", file_attr="image_file",
        log_label="Auto-downloaded IncenseProductImage",
    )


@receiver(post_delete, sender=IncenseProductImage)
def delete_incense_product_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)
    delete_url_from_storage(instance.image_url)


# --- Sports ---


@receiver(pre_save, sender=SportsProductImage)
def auto_download_sports_product_image(sender, instance, **kwargs):
    _auto_download_image_url_to_file(
        instance, url_attr="image_url", file_attr="image_file",
        log_label="Auto-downloaded SportsProductImage",
    )


@receiver(post_delete, sender=SportsProductImage)
def delete_sports_product_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)
    delete_url_from_storage(instance.image_url)


# --- Auto Parts ---


@receiver(pre_save, sender=AutoPartProductImage)
def auto_download_autopart_product_image(sender, instance, **kwargs):
    _auto_download_image_url_to_file(
        instance, url_attr="image_url", file_attr="image_file",
        log_label="Auto-downloaded AutoPartProductImage",
    )


@receiver(post_delete, sender=AutoPartProductImage)
def delete_autopart_product_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)
    delete_url_from_storage(instance.image_url)


# --- Headwear ---


@receiver(pre_save, sender=HeadwearProductImage)
def auto_download_headwear_product_image(sender, instance, **kwargs):
    _auto_download_image_url_to_file(
        instance, url_attr="image_url", file_attr="image_file",
        log_label="Auto-downloaded HeadwearProductImage",
    )


@receiver(post_delete, sender=HeadwearProductImage)
def delete_headwear_product_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)
    delete_url_from_storage(instance.image_url)


@receiver(post_delete, sender=HeadwearProduct)
def delete_headwear_product_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)
    if hasattr(instance, "main_video_file"):
        delete_file_from_storage(instance.main_video_file)
    delete_url_from_storage(getattr(instance, "main_image", ""))
    delete_url_from_storage(getattr(instance, "video_url", ""))


@receiver(post_delete, sender=HeadwearVariant)
def delete_headwear_variant_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)
    delete_url_from_storage(getattr(instance, "main_image", ""))


@receiver(post_delete, sender=HeadwearVariantImage)
def delete_headwear_variant_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)
    delete_url_from_storage(instance.image_url)


# --- Underwear ---


@receiver(pre_save, sender=UnderwearProductImage)
def auto_download_underwear_product_image(sender, instance, **kwargs):
    _auto_download_image_url_to_file(
        instance, url_attr="image_url", file_attr="image_file",
        log_label="Auto-downloaded UnderwearProductImage",
    )


@receiver(post_delete, sender=UnderwearProductImage)
def delete_underwear_product_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)
    delete_url_from_storage(instance.image_url)


@receiver(post_delete, sender=UnderwearProduct)
def delete_underwear_product_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)
    if hasattr(instance, "main_video_file"):
        delete_file_from_storage(instance.main_video_file)
    delete_url_from_storage(getattr(instance, "main_image", ""))
    delete_url_from_storage(getattr(instance, "video_url", ""))


@receiver(post_delete, sender=UnderwearVariant)
def delete_underwear_variant_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)
    delete_url_from_storage(getattr(instance, "main_image", ""))


@receiver(post_delete, sender=UnderwearVariantImage)
def delete_underwear_variant_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)
    delete_url_from_storage(instance.image_url)


# --- Islamic clothing ---


@receiver(post_delete, sender=IslamicClothingProduct)
def delete_islamic_clothing_product_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)
    if hasattr(instance, "main_video_file"):
        delete_file_from_storage(instance.main_video_file)
    delete_url_from_storage(getattr(instance, "main_image", ""))
    delete_url_from_storage(getattr(instance, "video_url", ""))


@receiver(post_delete, sender=IslamicClothingProductImage)
def delete_islamic_clothing_product_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)
    delete_url_from_storage(instance.image_url)


@receiver(post_delete, sender=IslamicClothingVariant)
def delete_islamic_clothing_variant_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)
    delete_url_from_storage(getattr(instance, "main_image", ""))


@receiver(post_delete, sender=IslamicClothingVariantImage)
def delete_islamic_clothing_variant_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)
    delete_url_from_storage(instance.image_url)


# --- Perfumery ---


@receiver(post_delete, sender=PerfumeryProduct)
def delete_perfumery_product_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)
    delete_url_from_storage(getattr(instance, "main_image", ""))


@receiver(post_delete, sender=PerfumeryProductImage)
def delete_perfumery_product_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)
    delete_url_from_storage(instance.image_url)


@receiver(post_delete, sender=PerfumeryVariant)
def delete_perfumery_variant_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)
    delete_url_from_storage(getattr(instance, "main_image", ""))


@receiver(post_delete, sender=PerfumeryVariantImage)
def delete_perfumery_variant_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)
    delete_url_from_storage(instance.image_url)


# --- Wave 2 simple domains ---


@receiver(post_delete, sender=MedicineProduct)
def delete_medicine_product_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)
    delete_url_from_storage(getattr(instance, "main_image", ""))


@receiver(post_delete, sender=MedicineProductImage)
def delete_medicine_product_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)
    delete_url_from_storage(instance.image_url)


@receiver(post_delete, sender=SupplementProduct)
def delete_supplement_product_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)
    delete_url_from_storage(getattr(instance, "main_image", ""))


@receiver(post_delete, sender=SupplementProductImage)
def delete_supplement_product_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)
    delete_url_from_storage(instance.image_url)


@receiver(post_delete, sender=MedicalEquipmentProduct)
def delete_medical_equipment_product_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)
    delete_url_from_storage(getattr(instance, "main_image", ""))


@receiver(post_delete, sender=MedicalEquipmentProductImage)
def delete_medical_equipment_product_image_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.image_file)
    delete_url_from_storage(instance.image_url)


@receiver(post_delete, sender=TablewareProduct)
def delete_tableware_product_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)
    delete_url_from_storage(getattr(instance, "main_image", ""))


@receiver(post_delete, sender=AccessoryProduct)
def delete_accessory_product_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)
    delete_url_from_storage(getattr(instance, "main_image", ""))


@receiver(post_delete, sender=IncenseProduct)
def delete_incense_product_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)
    delete_url_from_storage(getattr(instance, "main_image", ""))


@receiver(post_delete, sender=SportsProduct)
def delete_sports_product_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)
    delete_url_from_storage(getattr(instance, "main_image", ""))


@receiver(post_delete, sender=AutoPartProduct)
def delete_autopart_product_files(sender, instance, **kwargs):
    delete_file_from_storage(instance.main_image_file)
    delete_url_from_storage(getattr(instance, "main_image", ""))


# --- Banner ---


@receiver(pre_save, sender=BannerMedia)
def auto_download_banner_media_from_url(sender, instance, **kwargs):
    """
    Авто-скачивание медиа баннеров из внешних URL (Pinterest, и др.) → R2.

    Логика для каждого типа (image / video / gif):
      1. Если URL изменился — удаляем старый файл из R2.
      2. Если URL внешний, а файл ещё не загружен — скачиваем и помещаем в R2.

    Поля:
      image_url  → image      (ImageField,  upload_to=get_banner_image_upload_path)
      video_url  → video_file (FileField,   upload_to=get_banner_video_upload_path)
      gif_url    → gif_file   (FileField,   upload_to=get_banner_gif_upload_path)
    """
    # Получаем старое состояние из БД (только для существующих записей)
    old = None
    if instance.pk:
        try:
            old = BannerMedia.objects.only(
                "image_url", "image",
                "video_url", "video_file",
                "gif_url", "gif_file",
            ).get(pk=instance.pk)
        except BannerMedia.DoesNotExist:
            pass

    # ── image ──────────────────────────────────────────────────────────────
    if old and old.image and old.image.name:
        url_changed = (instance.image_url != old.image_url)
        file_cleared = not (instance.image and instance.image.name)
        if url_changed and file_cleared:
            delete_file_from_storage(old.image)
            logger.info("Deleted old BannerMedia.image from R2 (pk=%s)", instance.pk)

    if instance.image_url and not (instance.image and instance.image.name):
        if not is_internal_storage_url(instance.image_url):
            file_obj = _download_url_to_file(instance.image_url)
            if file_obj:
                _save_downloaded_file_to_storage(instance, "image", file_obj)
                logger.info(
                    "Auto-downloaded BannerMedia.image_url → image for banner %s (pk=%s)",
                    instance.banner_id, instance.pk or "new",
                )

    # ── video ──────────────────────────────────────────────────────────────
    if old and old.video_file and old.video_file.name:
        v_url_changed = (instance.video_url != old.video_url)
        v_file_cleared = not (instance.video_file and instance.video_file.name)
        if v_url_changed and v_file_cleared:
            delete_file_from_storage(old.video_file)
            logger.info("Deleted old BannerMedia.video_file from R2 (pk=%s)", instance.pk)

    if instance.video_url and not (instance.video_file and instance.video_file.name):
        if not is_internal_storage_url(instance.video_url):
            file_obj = _download_url_to_file(instance.video_url)
            if file_obj:
                _save_downloaded_file_to_storage(instance, "video_file", file_obj)
                logger.info(
                    "Auto-downloaded BannerMedia.video_url → video_file for banner %s (pk=%s)",
                    instance.banner_id, instance.pk or "new",
                )

    # ── gif ────────────────────────────────────────────────────────────────
    if old and old.gif_file and old.gif_file.name:
        g_url_changed = (instance.gif_url != old.gif_url)
        g_file_cleared = not (instance.gif_file and instance.gif_file.name)
        if g_url_changed and g_file_cleared:
            delete_file_from_storage(old.gif_file)
            logger.info("Deleted old BannerMedia.gif_file from R2 (pk=%s)", instance.pk)

    if instance.gif_url and not (instance.gif_file and instance.gif_file.name):
        if not is_internal_storage_url(instance.gif_url):
            file_obj = _download_url_to_file(instance.gif_url)
            if file_obj:
                _save_downloaded_file_to_storage(instance, "gif_file", file_obj)
                logger.info(
                    "Auto-downloaded BannerMedia.gif_url → gif_file for banner %s (pk=%s)",
                    instance.banner_id, instance.pk or "new",
                )


@receiver(post_delete, sender=BannerMedia)
def delete_banner_media_files(sender, instance, **kwargs):
    """Очищаем все файлы баннера из R2 при удалении записи."""
    delete_file_from_storage(instance.image)
    delete_file_from_storage(instance.video_file)
    delete_file_from_storage(instance.gif_file)
    # На случай если файл удалён, но URL остался — удаляем и по URL (если он внутренний)
    if not instance.image:
        delete_url_from_storage(instance.image_url)
    if not instance.video_file:
        delete_url_from_storage(instance.video_url)
    if not instance.gif_file:
        delete_url_from_storage(instance.gif_url)


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


@receiver(post_save, sender=Product)
def ensure_domain_product_for_base_product(sender, instance, **kwargs):
    """
    При сохранении Product (скрапер, импорт, админка) создаём запись в доменной
    модели (PerfumeryProduct, MedicineProduct и т.д.), если её ещё нет, чтобы
    товар отображался в нужном разделе админки и в правильном API.
    """
    from .domain_sync import ensure_domain_product_for_base
    ensure_domain_product_for_base(instance)


@receiver(post_save, sender=Product)
def sync_downloaded_video_to_book_product(sender, instance, **kwargs):
    """
    После скачивания видео на shadow Product путь main_video_file на BookProduct
    может указывать на отсутствующий объект в R2 (старая запись), а API отдаёт
    proxy-media → 404. Копируем реальный файл с Product на книгу, если у книги
    нет валидного файла в storage (админский загруженный файл не трогаем).
    """
    if instance.product_type != "books":
        return
    if not instance.main_video_file or not getattr(instance.main_video_file, "name", None):
        return
    from apps.catalog.utils.media_path import resolve_existing_media_storage_key

    if not resolve_existing_media_storage_key(instance.main_video_file.name):
        return
    book = BookProduct.objects.filter(base_product=instance).first()
    if not book:
        return
    bn = getattr(book.main_video_file, "name", None) or ""
    if bn and resolve_existing_media_storage_key(bn):
        return
    book.main_video_file = instance.main_video_file
    book.save(update_fields=["main_video_file"])


@receiver(post_save, sender=Product)
def ensure_product_price_info(sender, instance, **kwargs):
    """
    После сохранения Product создаём/обновляем запись ProductPrice (конвертация
    по валютам с маржой), чтобы невариативные товары отображались корректно
    при смене валюты на фронте и были в разделе «💰 Валюты — Цены товаров».
    """
    if instance.price is None or not instance.currency:
        return
    try:
        instance.update_currency_prices()
    except Exception as e:
        logger.exception("ensure_product_price_info: %s", e)


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
    # Удалить старые файлы из R2 при замене на URL или очистке
    if instance.pk:
        try:
            old = Product.objects.only("main_image", "main_image_file", "main_video_file", "video_url").get(pk=instance.pk)
            
            # Удаляем фото только если URL фото изменился ИЛИ был очищен, 
            # и при этом текущий instance.main_image_file пуст (что значит файл не был перекачан в этом сохранении)
            if old.main_image_file and old.main_image_file.name:
                url_changed = (instance.main_image != old.main_image)
                is_empty = not (instance.main_image_file and instance.main_image_file.name)
                # Если URL изменился на другой или на пустой, и в инстансе нет файла — удаляем старый
                if url_changed and is_empty:
                    delete_file_from_storage(old.main_image_file)
                    logger.info("Deleted old main_image_file for Product %s (URL changed or cleared)", instance.pk)
            
            if old.main_video_file and old.main_video_file.name:
                v_url_changed = (instance.video_url != old.video_url)
                v_is_empty = not (instance.main_video_file and instance.main_video_file.name)
                if v_url_changed and v_is_empty:
                    delete_file_from_storage(old.main_video_file)
                    logger.info("Deleted old main_video_file for Product %s (URL changed or cleared)", instance.pk)
        except Product.DoesNotExist:
            pass

    if instance.main_image and not instance.main_image_file:
        if not is_internal_storage_url(instance.main_image):
            file_obj = _download_url_to_file(instance.main_image)
            if file_obj:
                _save_downloaded_file_to_storage(instance, "main_image_file", file_obj)
                logger.info("Auto-downloaded main_image URL to main_image_file for Product %s", instance.id or "new")

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
