import csv
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import CommandError, call_command

from apps.catalog.management.commands import repair_broken_media
from apps.catalog.models import Category, MedicineProduct, MedicineProductImage
from apps.scrapers.models import ScraperConfig

CDN = "https://cdn.test"
LIVE = "products/medicines/gallery/live.jpg"


@pytest.fixture
def media(settings, tmp_path, monkeypatch):
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path), "base_url": "/media/"},
        },
    }
    settings.R2_CONFIG = {"public_url": CDN}
    (tmp_path / "products/medicines/gallery").mkdir(parents=True)
    (tmp_path / LIVE).write_bytes(b"live")
    monkeypatch.setattr(repair_broken_media, "MIN_STORAGE_OBJECTS", 1)
    monkeypatch.setattr(repair_broken_media, "MAX_BROKEN_SHARE", 1.0)

    def listing():
        keys = {}
        for path in tmp_path.rglob("*"):
            if path.is_file():
                keys[str(path.relative_to(tmp_path))] = path.stat().st_size
        return keys

    monkeypatch.setattr(repair_broken_media, "list_storage_objects", listing)
    return tmp_path


@pytest.fixture
def catalog(media):
    category = Category.objects.create(name="Лекарства", slug="medicines-test")
    with patch("apps.catalog.signals._download_url_to_file", return_value=None):
        plain = MedicineProduct.objects.create(name="Plain", slug="plain-med", category=category)
        redownload = MedicineProductImage.objects.create(
            product=plain, image_url="https://src.example/a.jpg", image_file="products/medicines/gone-a.jpg",
        )
        delete = MedicineProductImage.objects.create(
            product=plain, image_url=f"{CDN}/products/parsed/ilacfiyati/gone-b.jpg",
        )
        repoint = MedicineProductImage.objects.create(
            product=plain, image_url=f"{CDN}/products/medicines/gone-c.jpg", image_file=LIVE,
        )
        scraped = MedicineProduct.objects.create(
            name="Scraped", slug="scraped-med", category=category,
            external_url="https://ilacfiyati.com/ilaclar/scraped",
            main_image=f"{CDN}/products/medicines/gone-main.jpg",
        )
    ScraperConfig.objects.create(
        name="ilacfiyati-repair-test", parser_class="ilacfiyati", base_url="https://ilacfiyati.com",
        default_category=category, status="active", is_enabled=True,
    )
    return SimpleNamespace(
        category=category, redownload=redownload, delete=delete, repoint=repoint, scraped=scraped,
    )


def _report(path):
    return {
        (row["model"], row["pk"], row["fields"]): row
        for row in csv.DictReader(path.open(encoding="utf-8"))
    }


@pytest.mark.django_db
def test_dry_run_classifies_without_changes(catalog, tmp_path):
    report = tmp_path / "dry.csv"
    out = StringIO()
    with patch("apps.scrapers.services.ScraperIntegrationService.run_scraper") as run_scraper:
        call_command("repair_broken_media", "--report", str(report), stdout=out)

    run_scraper.assert_not_called()
    assert "DRY-RUN" in out.getvalue()
    rows = _report(report)
    image = "catalog.MedicineProductImage"
    assert rows[(image, str(catalog.redownload.pk), "image_file|image_url")]["action"] == "redownload"
    assert rows[(image, str(catalog.delete.pk), "image_file|image_url")]["action"] == "delete"
    assert rows[(image, str(catalog.repoint.pk), "image_file|image_url")]["action"] == "repoint"
    main = rows[("catalog.MedicineProduct", str(catalog.scraped.pk), "main_image_file|main_image")]
    assert main["action"] == "rescrape"
    assert main["source_url"] == "https://ilacfiyati.com/ilaclar/scraped"
    assert MedicineProductImage.objects.filter(pk=catalog.delete.pk).exists()


@pytest.mark.django_db
def test_apply_repairs_and_deletes_unrecoverable(catalog, tmp_path):
    completed = SimpleNamespace(status="completed")
    with patch(
        "apps.catalog.signals._download_url_to_file", return_value=ContentFile(b"img", name="a.jpg"),
    ), patch(
        "apps.scrapers.services.ScraperIntegrationService.run_scraper", return_value=completed,
    ) as run_scraper:
        call_command("repair_broken_media", "--apply", "--report", str(tmp_path / "a.csv"), stdout=StringIO())

    catalog.redownload.refresh_from_db()
    assert catalog.redownload.image_file.name != "products/medicines/gone-a.jpg"
    assert default_storage.exists(catalog.redownload.image_file.name)

    assert not MedicineProductImage.objects.filter(pk=catalog.delete.pk).exists()

    catalog.repoint.refresh_from_db()
    assert catalog.repoint.image_url == default_storage.url(LIVE)

    # Перескрейп (shadow Product и доменная карточка — один URL) не вернул картинку → поля очищены
    run_scraper.assert_called_once()
    assert run_scraper.call_args.kwargs["start_url"] == "https://ilacfiyati.com/ilaclar/scraped"
    assert run_scraper.call_args.kwargs["target_category"] == catalog.category
    catalog.scraped.refresh_from_db()
    assert catalog.scraped.main_image == ""
    assert not catalog.scraped.main_image_file


@pytest.mark.django_db
def test_no_rescrape_leaves_sourced_media_untouched(catalog, tmp_path):
    with patch("apps.catalog.signals._download_url_to_file", return_value=None), patch(
        "apps.scrapers.services.ScraperIntegrationService.run_scraper",
    ) as run_scraper:
        call_command(
            "repair_broken_media", "--apply", "--no-rescrape", "--report", str(tmp_path / "n.csv"),
            stdout=StringIO(),
        )

    run_scraper.assert_not_called()
    catalog.scraped.refresh_from_db()
    assert catalog.scraped.main_image.endswith("gone-main.jpg")


@pytest.mark.django_db
def test_refuses_to_run_on_empty_storage_listing(media, monkeypatch, tmp_path):
    monkeypatch.setattr(repair_broken_media, "MIN_STORAGE_OBJECTS", 1000)
    with pytest.raises(CommandError, match="подозрительно мал"):
        call_command("repair_broken_media", "--report", str(tmp_path / "r.csv"))
