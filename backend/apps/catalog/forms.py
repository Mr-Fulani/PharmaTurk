from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from django.utils.translation import gettext_lazy as _

from .models import Product, ProductImage


class ProductImageInlineFormSet(BaseInlineFormSet):
    """Формсет для изображений с дополнительной валидацией."""

    def clean(self):
        super().clean()
        images = [
            form for form in self.forms
            if not form.cleaned_data.get("DELETE", False) and form.cleaned_data.get("image_url")
        ]
        if len(images) > 5:
            raise ValidationError(_("Можно загрузить не более 5 изображений товара."))
        if images and not any(img.cleaned_data.get("is_main") for img in images):
            # Если в объекте уже есть main_image, не требуем is_main в галерее
            instance = getattr(self, "instance", None)
            has_main_field = getattr(instance, "main_image", None) if instance else None
            if not has_main_field:
                raise ValidationError(_("Необходимо отметить как минимум одно изображение как главное."))


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

