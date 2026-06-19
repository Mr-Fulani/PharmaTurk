"""
Tests for the media re-download fix in pre_save signals.

Core bug: when a file path is stored in the DB but the actual file is missing
from R2, the signals used to skip the download. These tests verify the fix:
any model with an external URL will re-download if R2 doesn't have the file.
"""
import pytest
from unittest.mock import MagicMock, patch

from apps.catalog.signals import is_internal_storage_url


class TestIsInternalStorageUrl:
    def test_external_cdn_with_media_path_is_not_internal(self):
        # FLO CDN: путь /media/, но хост внешний → НЕ внутренний (иначе не качается)
        assert is_internal_storage_url(
            "https://floimages.mncdn.com/media/catalog/product/x.jpg"
        ) is False

    def test_relative_media_path_is_internal(self):
        assert is_internal_storage_url("/media/products/x.jpg") is True

    def test_relative_products_path_is_internal(self):
        assert is_internal_storage_url("/products/shoes/x.jpg") is True

    def test_external_without_media_path_is_not_internal(self):
        assert is_internal_storage_url("https://static.zara.net/photos/x.jpg") is False


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_field(name=None, committed=True):
    """Minimal FieldFile mock."""
    f = MagicMock()
    f.name = name
    f._committed = committed
    # FieldFile is truthy only when it has a name
    f.__bool__ = lambda self: bool(self.name)
    return f


# ── _file_missing_from_storage ─────────────────────────────────────────────────

class TestFileMissingFromStorage:
    @pytest.fixture(autouse=True)
    def fn(self):
        from apps.catalog.signals import _file_missing_from_storage
        self._fn = _file_missing_from_storage

    def test_new_admin_upload_is_never_missing(self):
        """_committed=False means the file was just selected in admin and not yet
        saved to R2 — we must not overwrite it with an external URL download."""
        field = _make_field(name="some/path.jpg", committed=False)
        assert self._fn(field) is False

    def test_empty_field_is_not_missing(self):
        """An empty field (no name) is not 'missing' — just not set."""
        field = _make_field(name=None)
        with patch("django.core.files.storage.default_storage") as mock_storage:
            assert self._fn(field) is False
            mock_storage.exists.assert_not_called()

    def test_returns_true_when_path_set_but_r2_has_no_file(self):
        field = _make_field(name="marketing/cards/brand/logo.jpg")
        with patch("django.core.files.storage.default_storage") as mock_storage:
            mock_storage.exists.return_value = False
            assert self._fn(field) is True

    def test_returns_false_when_path_set_and_r2_has_file(self):
        field = _make_field(name="marketing/cards/brand/logo.jpg")
        with patch("django.core.files.storage.default_storage") as mock_storage:
            mock_storage.exists.return_value = True
            assert self._fn(field) is False

    def test_exception_returns_false(self):
        """Storage errors must not break signal execution."""
        field = _make_field(name="some/path.jpg")
        with patch("django.core.files.storage.default_storage") as mock_storage:
            mock_storage.exists.side_effect = Exception("connection error")
            assert self._fn(field) is False


# ── _auto_download_impl ────────────────────────────────────────────────────────
# Used by: ClothingProductImage, ClothingVariantImage, ElectronicsProductImage,
#          FurnitureVariantImage, JewelryProductImage, JewelryVariantImage,
#          ShoeProductImage, ShoeVariantImage, ServiceImage

class TestAutoDownloadImpl:

    def _run(self, url, file_val, storage_exists):
        from apps.catalog.signals import _auto_download_impl

        instance = MagicMock()
        instance.image_url = url
        instance.image_file = file_val

        mock_file_obj = MagicMock()

        with patch("apps.catalog.signals._file_missing_from_storage", return_value=not storage_exists), \
             patch("apps.catalog.signals.is_internal_storage_url", return_value=False), \
             patch("apps.catalog.signals._download_url_to_file", return_value=mock_file_obj) as mock_dl, \
             patch("apps.catalog.signals._save_downloaded_file_to_storage") as mock_save:
            _auto_download_impl(instance)
            return mock_dl.called, mock_save.called

    def test_downloads_when_url_set_and_file_empty(self):
        downloaded, saved = self._run(
            url="https://ext.com/img.jpg", file_val=None, storage_exists=True
        )
        assert downloaded and saved

    def test_redownloads_when_path_set_but_file_missing_from_r2(self):
        """The core fix: re-download when DB has a path but R2 is empty."""
        file_val = _make_field(name="products/img.jpg")
        downloaded, saved = self._run(
            url="https://ext.com/img.jpg", file_val=file_val, storage_exists=False
        )
        assert downloaded and saved

    def test_skips_when_file_exists_in_r2(self):
        file_val = _make_field(name="products/img.jpg")
        downloaded, saved = self._run(
            url="https://ext.com/img.jpg", file_val=file_val, storage_exists=True
        )
        assert not downloaded and not saved

    def test_skips_when_no_url(self):
        downloaded, saved = self._run(url=None, file_val=None, storage_exists=True)
        assert not downloaded and not saved

    def test_skips_internal_url(self):
        from apps.catalog.signals import _auto_download_impl

        instance = MagicMock()
        instance.image_url = "https://cdn.mudaroba.com/products/img.jpg"
        instance.image_file = None

        with patch("apps.catalog.signals._file_missing_from_storage", return_value=False), \
             patch("apps.catalog.signals.is_internal_storage_url", return_value=True), \
             patch("apps.catalog.signals._download_url_to_file") as mock_dl:
            _auto_download_impl(instance)
            # Internal URL branch may set path without downloading via HTTP
            mock_dl.assert_not_called()


# ── ProductImage signal ────────────────────────────────────────────────────────

class TestProductImageSignal:

    def _run(self, image_url, image_file, storage_exists):
        from apps.catalog.signals import auto_download_product_image_from_url

        instance = MagicMock()
        instance.image_url = image_url
        instance.image_file = image_file

        mock_file_obj = MagicMock()

        with patch("apps.catalog.signals._file_missing_from_storage", return_value=not storage_exists), \
             patch("apps.catalog.signals.is_internal_storage_url", return_value=False), \
             patch("apps.catalog.signals._download_url_to_file", return_value=mock_file_obj) as mock_dl, \
             patch("apps.catalog.signals._save_downloaded_file_to_storage") as mock_save:
            auto_download_product_image_from_url(sender=None, instance=instance)
            return mock_dl.called, mock_save.called

    def test_downloads_when_image_file_empty(self):
        downloaded, saved = self._run(
            image_url="https://ext.com/img.jpg", image_file=None, storage_exists=True
        )
        assert downloaded and saved

    def test_redownloads_when_path_set_but_file_missing_from_r2(self):
        image_file = _make_field(name="products/parsed/img.jpg")
        downloaded, saved = self._run(
            image_url="https://ext.com/img.jpg", image_file=image_file, storage_exists=False
        )
        assert downloaded and saved

    def test_skips_when_file_exists_in_r2(self):
        image_file = _make_field(name="products/parsed/img.jpg")
        downloaded, saved = self._run(
            image_url="https://ext.com/img.jpg", image_file=image_file, storage_exists=True
        )
        assert not downloaded and not saved


# ── BannerMedia signal ─────────────────────────────────────────────────────────

class TestBannerMediaSignal:

    def _run(self, image_url, image_field_name, storage_exists):
        from apps.catalog.signals import auto_download_banner_media_from_url
        from apps.catalog.models import BannerMedia

        image = _make_field(name=image_field_name)
        instance = MagicMock()
        instance.image_url = image_url
        instance.image = image
        instance.pk = 1
        instance.banner_id = 1
        # video/gif fields — set them so those branches are skipped
        instance.video_url = None
        instance.gif_url = None

        mock_file_obj = MagicMock()

        with patch("apps.catalog.signals._file_missing_from_storage", return_value=not storage_exists), \
             patch("apps.catalog.signals.is_internal_storage_url", return_value=False), \
             patch("apps.catalog.signals._download_url_to_file", return_value=mock_file_obj) as mock_dl, \
             patch("apps.catalog.signals._save_downloaded_file_to_storage") as mock_save, \
             patch("apps.catalog.signals.BannerMedia") as mock_model:
            # Simulate no old instance so deletion branch is skipped cleanly
            mock_model.DoesNotExist = BannerMedia.DoesNotExist
            mock_model.objects.only.return_value.get.side_effect = BannerMedia.DoesNotExist
            auto_download_banner_media_from_url(sender=None, instance=instance)
            return mock_dl.called, mock_save.called

    def test_downloads_when_image_empty(self):
        downloaded, saved = self._run(
            image_url="https://ext.com/banner.jpg", image_field_name=None, storage_exists=True
        )
        assert downloaded and saved

    def test_redownloads_when_path_set_but_missing_from_r2(self):
        downloaded, saved = self._run(
            image_url="https://ext.com/banner.jpg",
            image_field_name="marketing/banners/banner.jpg",
            storage_exists=False,
        )
        assert downloaded and saved

    def test_skips_when_file_exists_in_r2(self):
        downloaded, saved = self._run(
            image_url="https://ext.com/banner.jpg",
            image_field_name="marketing/banners/banner.jpg",
            storage_exists=True,
        )
        assert not downloaded and not saved


# ── New admin upload protection ────────────────────────────────────────────────

class TestNewAdminUploadProtection:
    """When an admin uploads a file directly, _committed=False.
    The signal must NOT overwrite it by downloading from external_url."""

    def test_catalog_auto_download_impl_skips_uncommitted_file(self):
        from apps.catalog.signals import _auto_download_impl

        # Simulate a fresh admin upload: field has a name but _committed=False
        file_val = _make_field(name="tmp_upload.jpg", committed=False)

        instance = MagicMock()
        instance.image_url = "https://ext.com/img.jpg"
        instance.image_file = file_val

        with patch("apps.catalog.signals.is_internal_storage_url", return_value=False), \
             patch("apps.catalog.signals._download_url_to_file") as mock_dl:
            _auto_download_impl(instance)
            mock_dl.assert_not_called()

    def test_feedback_file_missing_helper_skips_uncommitted_file(self):
        from apps.feedback.signals import _file_missing_from_storage

        field = _make_field(name="testimonials/img.jpg", committed=False)
        assert _file_missing_from_storage(field) is False


# ── feedback/signals.py TestimonialMedia ───────────────────────────────────────

class TestTestimonialMediaSignal:

    def _run(self, media_type, image_field_name, video_file_name, video_url, storage_exists):
        from apps.feedback.signals import auto_download_testimonial_media

        image = _make_field(name=image_field_name)
        video_file = _make_field(name=video_file_name)

        instance = MagicMock()
        instance.media_type = media_type
        instance.image = image
        instance.video_file = video_file
        instance.video_url = video_url

        with patch("apps.feedback.signals._file_missing_from_storage", return_value=not storage_exists), \
             patch("apps.feedback.signals._is_internal_url", return_value=False), \
             patch("apps.feedback.signals._download_and_save") as mock_dl:
            auto_download_testimonial_media(sender=None, instance=instance)
            return mock_dl.called

    def test_image_downloads_when_empty(self):
        downloaded = self._run(
            media_type="image",
            image_field_name=None,
            video_file_name=None,
            video_url="https://ext.com/review.jpg",
            storage_exists=True,
        )
        assert downloaded

    def test_image_redownloads_when_missing_from_r2(self):
        downloaded = self._run(
            media_type="image",
            image_field_name="testimonials/review.jpg",
            video_file_name=None,
            video_url="https://ext.com/review.jpg",
            storage_exists=False,
        )
        assert downloaded

    def test_image_skips_when_exists_in_r2(self):
        downloaded = self._run(
            media_type="image",
            image_field_name="testimonials/review.jpg",
            video_file_name=None,
            video_url="https://ext.com/review.jpg",
            storage_exists=True,
        )
        assert not downloaded

    def test_video_downloads_when_empty(self):
        downloaded = self._run(
            media_type="video_file",
            image_field_name=None,
            video_file_name=None,
            video_url="https://ext.com/review.mp4",
            storage_exists=True,
        )
        assert downloaded

    def test_video_redownloads_when_missing_from_r2(self):
        downloaded = self._run(
            media_type="video_file",
            image_field_name=None,
            video_file_name="testimonials/review.mp4",
            video_url="https://ext.com/review.mp4",
            storage_exists=False,
        )
        assert downloaded

    def test_video_skips_when_exists_in_r2(self):
        downloaded = self._run(
            media_type="video_file",
            image_field_name=None,
            video_file_name="testimonials/review.mp4",
            video_url="https://ext.com/review.mp4",
            storage_exists=True,
        )
        assert not downloaded

    def test_youtube_url_is_never_downloaded(self):
        """YouTube/Vimeo embed links must never be downloaded to R2."""
        from apps.feedback.signals import auto_download_testimonial_media

        instance = MagicMock()
        instance.media_type = "video_file"
        instance.image = _make_field(name=None)
        instance.video_file = _make_field(name=None)
        instance.video_url = "https://www.youtube.com/watch?v=abc123"

        with patch("apps.feedback.signals._file_missing_from_storage", return_value=True), \
             patch("apps.feedback.signals._is_internal_url", return_value=False), \
             patch("apps.feedback.signals._download_and_save") as mock_dl:
            auto_download_testimonial_media(sender=None, instance=instance)
            mock_dl.assert_not_called()
