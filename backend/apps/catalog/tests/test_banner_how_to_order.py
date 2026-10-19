import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Banner, BannerMedia, BannerMediaTranslation


def _banner(position, *, is_active=True, title="Слайд"):
    banner = Banner.objects.create(position=position, is_active=is_active)
    media = BannerMedia.objects.create(
        banner=banner,
        content_type="image",
        image_url="https://cdn.mudaroba.com/banners/how-to-order.webp",
        title=title,
        link_url="https://mudaroba.com/how-to-order-medicines#sourcing",
        link_text="Оставить заявку",
    )
    return banner, media


@pytest.mark.django_db
def test_how_to_order_position_returns_only_its_active_banners_with_translations():
    banner, media = _banner("how_to_order", title="Подбор препаратов")
    BannerMediaTranslation.objects.create(
        banner_media=media, locale="en", title="Medicine sourcing", link_text="Send a request"
    )
    _banner("how_to_order", is_active=False, title="Выключенный")
    _banner("main", title="Главная")

    client = APIClient()
    ru = client.get("/api/catalog/banners", {"position": "how_to_order"}, HTTP_ACCEPT_LANGUAGE="ru")
    en = client.get("/api/catalog/banners", {"position": "how_to_order"}, HTTP_ACCEPT_LANGUAGE="en")

    assert ru.status_code == 200
    assert [item["id"] for item in ru.json()] == [banner.id]
    assert ru.json()[0]["media_files"][0]["title"] == "Подбор препаратов"
    assert en.json()[0]["media_files"][0]["title"] == "Medicine sourcing"
    assert en.json()[0]["media_files"][0]["link_text"] == "Send a request"


def test_how_to_order_position_is_selectable_in_admin():
    assert "how_to_order" in dict(Banner.POSITION_CHOICES)
