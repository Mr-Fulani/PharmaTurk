from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from django.utils.translation import gettext_lazy as _

from .models import (
    Product,
    ProductImage,
    ClothingVariantImage,
    ShoeVariantImage,
    Category,
    validate_card_media_file_size,
)


def _parent_has_main_media(formset, url_attr="main_image", file_attr="main_image_file"):
    """Проверяет, что у родительской формы заполнено главное медиа: изображение или видео (из instance или request)."""
    def has_media(url_key, file_key):
        if instance:
            if getattr(instance, url_key, None):
                return True
            f = getattr(instance, file_key, None)
            if f and (hasattr(f, "name") and f.name):
                return True
        if data.get(url_key) and str(data.get(url_key)).strip():
            return True
        if files.get(file_key):
            return True
        return False

    instance = getattr(formset, "instance", None)
    data = getattr(formset, "data", None) or {}
    files = getattr(formset, "files", None) or {}
    if has_media(url_attr, file_attr):
        return True
    if has_media("video_url", "main_video_file"):
        return True
    return False


class ProductImageInlineFormSet(BaseInlineFormSet):
    """Формсет для изображений с дополнительной валидацией."""

    def clean(self):
        super().clean()
        active_forms = [
            form for form in self.forms
            if not form.cleaned_data.get("DELETE", False)
        ]
        media_items = [
            form for form in active_forms
            if (
                form.cleaned_data.get("image_url")
                or form.cleaned_data.get("image_file")
                or form.cleaned_data.get("video_url")
                or form.cleaned_data.get("video_file")
            )
        ]
        for form in media_items:
            image_file = form.cleaned_data.get("image_file")
            if image_file:
                validate_card_media_file_size(image_file)
            video_file = form.cleaned_data.get("video_file")
            if video_file:
                validate_card_media_file_size(video_file)
        if len(media_items) > 5:
            raise ValidationError(_("Можно загрузить не более 5 медиафайлов товара."))
        images = [
            form for form in active_forms
            if form.cleaned_data.get("image_url") or form.cleaned_data.get("image_file")
        ]
        if images and not any(img.cleaned_data.get("is_main") for img in images):
            if not _parent_has_main_media(self):
                raise ValidationError(_("Необходимо отметить как минимум одно изображение как главное, или заполнить поле 'Главное изображение (файл)'."))


class VariantImageInlineFormSet(BaseInlineFormSet):
    """Формсет для изображений вариантов (та же логика, что и для товаров)."""

    def clean(self):
        super().clean()
        active_forms = [
            form for form in self.forms
            if not form.cleaned_data.get("DELETE", False)
        ]
        images = [
            form for form in active_forms
            if form.cleaned_data.get("image_url") or form.cleaned_data.get("image_file")
        ]
        for form in images:
            image_file = form.cleaned_data.get("image_file")
            if image_file:
                validate_card_media_file_size(image_file)
        if len(images) > 5:
            raise ValidationError(_("Можно загрузить не более 5 изображений варианта."))
        if images and not any(img.cleaned_data.get("is_main") for img in images):
            if not _parent_has_main_media(self):
                raise ValidationError(_("Необходимо отметить как минимум одно изображение варианта как главное, или заполнить поле 'Главное изображение (файл)'."))


class ProductForm(forms.ModelForm):
    """Форма для админки товара с дополнительной информацией."""

    class Meta:
        model = Product
        fields = "__all__"
        help_texts = {
            "meta_title": _("Применяется для SEO title на английском, оставьте пустым для автогенерации."),
            "meta_description": _("Англоязычное описание для поисковиков."),
            "og_description": _("OpenGraph description (англ.), отображается в соцсетях."),
            "og_image_url": _("Ссылка на изображение для Open Graph, если оно отличается от основного."),
        }

    def clean_min_order_quantity(self):
        value = self.cleaned_data.get("min_order_quantity")
        if value is not None and value < 1:
            raise ValidationError(_("Минимальное количество заказа должно быть не меньше 1."))
        return value


class CategoryForm(forms.ModelForm):
    """Форма для категории с валидацией типа."""
    
    class Meta:
        model = Category
        fields = "__all__"
    
    def clean_category_type(self):
        category_type = self.cleaned_data.get("category_type")
        if not category_type:
            raise ValidationError(_("Необходимо выбрать тип категории! Если нужного типа нет, создайте его в разделе 'Типы категорий'."))
        return category_type
