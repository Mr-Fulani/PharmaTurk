from django.forms.models import BaseInlineFormSet
from django.forms import modelform_factory

from apps.catalog.models import JewelryProductImage, JewelryVariantImage
from apps.catalog.forms import ProductImageInlineFormSet, VariantImageInlineFormSet


class _FakeMediaForm:
    def __init__(self, *, image_url="", image_file=None, video_url="", video_file=None, is_main=False, delete=False):
        self.cleaned_data = {
            "image_url": image_url,
            "image_file": image_file,
            "video_url": video_url,
            "video_file": video_file,
            "is_main": is_main,
            "DELETE": delete,
        }


class _FakeVariantForm:
    def __init__(self, *, image_url="", image_file=None, is_main=False, delete=False):
        self.cleaned_data = {
            "image_url": image_url,
            "image_file": image_file,
            "is_main": is_main,
            "DELETE": delete,
        }


def _patch_base_clean(monkeypatch):
    monkeypatch.setattr(BaseInlineFormSet, "clean", lambda self: None)


def test_product_image_formset_allows_more_than_five_media(monkeypatch):
    _patch_base_clean(monkeypatch)

    formset = ProductImageInlineFormSet.__new__(ProductImageInlineFormSet)
    formset.forms = [
        _FakeMediaForm(image_url=f"https://example.com/{idx}.jpg", is_main=(idx == 0))
        for idx in range(6)
    ]
    formset.instance = None
    formset.data = {}
    formset.files = {}

    formset.clean()


def test_variant_image_formset_allows_more_than_five_images(monkeypatch):
    _patch_base_clean(monkeypatch)

    formset = VariantImageInlineFormSet.__new__(VariantImageInlineFormSet)
    formset.forms = [
        _FakeVariantForm(image_url=f"https://example.com/{idx}.jpg", is_main=(idx == 0))
        for idx in range(6)
    ]
    formset.instance = None
    formset.data = {}
    formset.files = {}

    formset.clean()


def test_jewelry_image_url_is_optional_when_uploading_file():
    product_form = modelform_factory(JewelryProductImage, fields=("image_file", "image_url"))
    variant_form = modelform_factory(JewelryVariantImage, fields=("image_file", "image_url"))

    assert product_form.base_fields["image_url"].required is False
    assert variant_form.base_fields["image_url"].required is False
