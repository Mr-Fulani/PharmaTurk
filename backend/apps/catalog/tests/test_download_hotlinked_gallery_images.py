import csv
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.files.storage import default_storage
from django.core.management import CommandError, call_command

from apps.catalog.management.commands import download_hotlinked_gallery_images as command
from apps.catalog.models import (
    Category,
    ClothingProduct,
    ClothingVariant,
    ClothingVariantImage,
    HeadwearProduct,
    HeadwearVariant,
    HeadwearVariantImage,
)
from apps.catalog.serializers import HeadwearVariantImageSerializer

CDN = "https://cdn.test"
LCW = "https://img-lcwaikiki.mncdn.com/mnpadding/1020/1360/ffffff/pim/productimages/1/kepka_a.jpg"
ZARA = "https://static.zara.net/assets/public/1/shirt.jpg"


@pytest.fixture
def catalog(settings, tmp_path):
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path), "base_url": "/media/"},
        },
    }
    settings.R2_CONFIG = {"public_url": CDN}
    category = Category.objects.create(name="Кепки", slug="hotlink-caps")
    # Источник не отдал файл сигналу — строка остаётся со ссылкой на сайт продавца.
    with patch("apps.catalog.signals._download_url_to_file", return_value=None):
        cap = HeadwearProduct.objects.create(name="Кепка", slug="hotlink-kepka", category=category)
        cap_variant = HeadwearVariant.objects.create(product=cap, slug="hotlink-kepka-black", color="Black")
        lcw = HeadwearVariantImage.objects.create(variant=cap_variant, image_url=LCW)
        own = HeadwearVariantImage.objects.create(
            variant=cap_variant, image_url=f"{CDN}/products/headwear/own.jpg", sort_order=1,
        )
        shirt = ClothingProduct.objects.create(name="Рубашка", slug="hotlink-shirt", category=category)
        shirt_variant = ClothingVariant.objects.create(product=shirt, slug="hotlink-shirt-white", color="White")
        zara = ClothingVariantImage.objects.create(variant=shirt_variant, image_url=ZARA)
    assert not lcw.image_file and not zara.image_file
    return SimpleNamespace(lcw=lcw, own=own, zara=zara)


def _response(status=200, content_type="image/jpeg", content=b"jpeg-bytes"):
    return SimpleNamespace(status_code=status, headers={"Content-Type": content_type}, content=content)


def _run(tmp_path, *args):
    report = tmp_path / "report.csv"
    out = StringIO()
    call_command("download_hotlinked_gallery_images", *args, "--report", str(report), stdout=out)
    rows = {row["pk"] + row["model"]: row for row in csv.DictReader(report.open(encoding="utf-8"))}
    return out.getvalue(), rows


@pytest.mark.django_db
def test_dry_run_reports_without_network_and_changes(catalog, tmp_path):
    with patch.object(command.requests, "get") as get:
        out, rows = _run(tmp_path)

    get.assert_not_called()
    assert "DRY-RUN" in out
    assert len(rows) == 2  # строка с адресом нашего хранилища — не к продавцу
    assert rows[f"{catalog.lcw.pk}catalog.HeadwearVariantImage"]["result"] == "would_download"
    assert rows[f"{catalog.zara.pk}catalog.ClothingVariantImage"]["result"] == "needs_proxy"
    catalog.lcw.refresh_from_db()
    assert not catalog.lcw.image_file


@pytest.mark.django_db
def test_apply_downloads_copy_and_page_stops_using_seller_url(catalog, tmp_path):
    with patch.object(command.requests, "get", return_value=_response()) as get:
        _, rows = _run(tmp_path, "--apply")

    # Zara без флага не трогаем: один запрос — только LC Waikiki, напрямую и без Referer.
    get.assert_called_once()
    assert get.call_args.args == (LCW,)
    assert get.call_args.kwargs["proxies"] is None
    assert set(get.call_args.kwargs["headers"]) == {"User-Agent"}

    catalog.lcw.refresh_from_db()
    assert catalog.lcw.image_url == LCW
    assert default_storage.exists(catalog.lcw.image_file.name)
    row = rows[f"{catalog.lcw.pk}catalog.HeadwearVariantImage"]
    assert row["result"] == "downloaded" and row["image_file"] == catalog.lcw.image_file.name
    shown = HeadwearVariantImageSerializer(catalog.lcw, context={}).data["image_url"]
    assert "mncdn.com" not in shown and catalog.lcw.image_file.name in shown

    catalog.zara.refresh_from_db()
    assert not catalog.zara.image_file
    assert rows[f"{catalog.zara.pk}catalog.ClothingVariantImage"]["result"] == "needs_proxy"


@pytest.mark.django_db
def test_failed_download_leaves_row_untouched(catalog, tmp_path):
    with patch.object(command.requests, "get", return_value=_response(status=403)):
        _, rows = _run(tmp_path, "--apply", "--host", "img-lcwaikiki.mncdn.com")

    assert len(rows) == 1
    assert rows[f"{catalog.lcw.pk}catalog.HeadwearVariantImage"]["result"] == "failed:http_403"
    catalog.lcw.refresh_from_db()
    assert not catalog.lcw.image_file


@pytest.mark.django_db
def test_zara_goes_through_proxy_only_with_flag(catalog, tmp_path, settings):
    settings.SCRAPER_PROXY_URL = ""
    with pytest.raises(CommandError):
        _run(tmp_path, "--apply", "--zara-via-proxy")

    settings.SCRAPER_PROXY_URL = "http://proxy.test:1"
    settings.SCRAPER_PROXY_CA_BUNDLE = "/ca.pem"
    with patch.object(command.requests, "get", return_value=_response()) as get:
        _, rows = _run(tmp_path, "--apply", "--zara-via-proxy", "--host", "static.zara.net")

    get.assert_called_once()
    assert get.call_args.kwargs["proxies"] == {"http": "http://proxy.test:1", "https": "http://proxy.test:1"}
    assert get.call_args.kwargs["verify"] == "/ca.pem"
    assert rows[f"{catalog.zara.pk}catalog.ClothingVariantImage"]["result"] == "downloaded"
    catalog.zara.refresh_from_db()
    assert default_storage.exists(catalog.zara.image_file.name)
