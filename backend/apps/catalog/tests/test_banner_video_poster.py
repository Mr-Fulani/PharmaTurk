import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Banner, BannerMedia
from apps.catalog.utils.storage_paths import get_banner_poster_upload_path

POSTER = "marketing/banners/after_brands/posters/after_brands-poster-1.webp"


@pytest.mark.django_db
def test_video_banner_returns_poster_url_only_for_video_with_poster():
    banner = Banner.objects.create(position="after_brands", is_active=True)
    with_poster = BannerMedia.objects.create(
        banner=banner, content_type="video", sort_order=0,
        video_url="https://cdn.mudaroba.com/marketing/banners/after_brands/videos/a.mp4",
        video_poster=POSTER,
    )
    without_poster = BannerMedia.objects.create(
        banner=banner, content_type="video", sort_order=1,
        video_url="https://cdn.mudaroba.com/marketing/banners/after_brands/videos/b.mp4",
    )
    image_slide = BannerMedia.objects.create(
        banner=banner, content_type="image", sort_order=2,
        image_url="https://cdn.mudaroba.com/banners/slide.webp",
        video_poster=POSTER,
    )

    response = APIClient().get("/api/catalog/banners", {"position": "after_brands"})

    assert response.status_code == 200
    media = {item["id"]: item for item in response.json()[0]["media_files"]}
    assert media[with_poster.id]["poster_url"].endswith(f"/{POSTER}")
    assert media[with_poster.id]["poster_url"].startswith("http")
    assert media[without_poster.id]["poster_url"] == ""
    assert media[image_slide.id]["poster_url"] == ""


def test_poster_upload_path_is_next_to_banner_videos():
    banner = Banner(position="before_footer", title="Акция")
    path = get_banner_poster_upload_path(BannerMedia(banner=banner), "frame.webp")

    assert path.startswith("marketing/banners/before_footer/posters/")
    assert path.endswith(".webp")
