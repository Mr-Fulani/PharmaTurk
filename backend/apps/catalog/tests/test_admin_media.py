from types import SimpleNamespace

from django.test import override_settings

from apps.catalog.admin_media import resolve_media_url


def test_admin_media_uses_proxy_for_file_field():
    obj = SimpleNamespace(
        image_file=SimpleNamespace(name="products/accessories/belt/image.jpg"),
        image_url="https://broken.example/image.jpg",
    )

    assert resolve_media_url(obj, "image_file", "image_url") == (
        "/api/catalog/proxy-media/?path="
        "products%2Faccessories%2Fbelt%2Fimage.jpg"
    )


@override_settings(R2_PUBLIC_URL="https://cdn.mudaroba.com", R2_CONFIG={})
def test_admin_media_uses_proxy_for_internal_cdn_url_without_file_field():
    obj = SimpleNamespace(
        image_file=None,
        image_url="https://cdn.mudaroba.com/products/accessories/belt/image.jpg",
    )

    assert resolve_media_url(obj, "image_file", "image_url") == (
        "/api/catalog/proxy-media/?path="
        "products%2Faccessories%2Fbelt%2Fimage.jpg"
    )


def test_admin_media_keeps_external_source_url():
    obj = SimpleNamespace(
        image_file=None,
        image_url="https://img-lcwaikiki.mncdn.com/product.jpg",
    )

    assert resolve_media_url(obj, "image_file", "image_url") == obj.image_url
