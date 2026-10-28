"""Удаление неактуальных товаров: только по решению владельца и за предохранителями."""
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.utils import timezone

from apps.catalog.models import Product, ProductImage, ProductSourceOffer
from apps.catalog.models_stock import ProductDeletionLog, StaleProductCandidate
from apps.catalog.services import stale_products
from apps.catalog.services.stale_products import (
    StaleProductsRefused,
    delete_candidates,
    hide_candidates,
    keep_candidates,
    plan_action,
    refresh_media_stats,
    restore_deletion,
)
from apps.catalog.utils.media_references import MediaReferenceCheckError
from apps.orders.models import Cart, CartItem


@pytest.fixture(autouse=True)
def stale_settings(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": f"stale-products-{uuid4().hex}",
        }
    }
    settings.STALE_PRODUCT_MIN_DAYS = 7
    settings.STALE_PRODUCT_DELETE_AFTER_HIDDEN_DAYS = 14
    settings.STALE_PRODUCT_MAX_PER_ACTION = 200
    settings.STALE_PRODUCT_MAX_SOURCE_PERCENT = 50
    settings.STALE_PRODUCT_MIN_CATALOG_PRODUCTS = 1
    cache.clear()
    yield
    cache.clear()


class FakeGateway:
    """R2 и бакет бэкапов в памяти."""

    def __init__(self, files):
        self.files = dict(files)
        self.backups = {}
        self.deleted = []
        self.fail_backup = set()

    def check_ready(self):
        pass

    def size(self, path):
        return self.files.get(path)

    def backup(self, path):
        if path in self.fail_backup:
            raise RuntimeError("backup bucket unavailable")
        size = self.files.get(path)
        if size is not None:
            self.backups[path] = size
        return size

    def delete(self, path):
        self.deleted.append(path)
        self.files.pop(path, None)

    def restore(self, path):
        if path in self.files:
            return False
        self.files[path] = self.backups[path]
        return True


def _product(index, *, images=()):
    url = f"https://www.lcw.com/urun-{index}-o-{index}"
    product = Product.objects.create(
        name=f"LCW tabak {index}",
        slug=f"lcw-tabak-{index}-{uuid4().hex[:8]}",
        product_type="tableware",
        price=Decimal("100.00"),
        currency="TRY",
        external_id=f"lcw-{index}",
        external_url=url,
        is_available=True,
    )
    ProductSourceOffer.objects.create(
        product=product,
        parser_key="lcw",
        canonical_url=url,
        source_domain="www.lcw.com",
        external_product_id=f"lcw-{index}",
        source_price=Decimal("100.00"),
        source_currency="TRY",
    )
    for order, name in enumerate(images):
        ProductImage.objects.create(product=product, image_file=name, sort_order=order)
    return product


def _candidate(product, *, gone_days=10, hidden_days=None, status=None):
    now = timezone.now()
    candidate = StaleProductCandidate.objects.create(
        product=product,
        parser_key="lcw",
        source_url=product.external_url,
        first_seen_at=now - timedelta(days=gone_days),
        last_gone_at=now - timedelta(hours=6),
        status=status or (
            StaleProductCandidate.Status.HIDDEN if hidden_days is not None else StaleProductCandidate.Status.CANDIDATE
        ),
        hidden_at=now - timedelta(days=hidden_days) if hidden_days is not None else None,
    )
    if hidden_days is not None:
        Product.objects.filter(pk=product.pk).update(is_active=False)
    return candidate


def _catalog(count):
    """Другие товары источника — чтобы удаляемые были малой долей каталога."""
    return [_product(1000 + index) for index in range(count)]


# --- шаг 1: скрыть -----------------------------------------------------------------------


@pytest.mark.django_db
def test_hide_needs_days_at_seller_and_a_recent_check():
    _catalog(10)
    fresh = _candidate(_product(1), gone_days=2)
    stale_check = _candidate(_product(2))
    StaleProductCandidate.objects.filter(pk=stale_check.pk).update(last_gone_at=timezone.now() - timedelta(days=5))
    ready = _candidate(_product(3))

    plan = hide_candidates([fresh.pk, stale_check.pk, ready.pk])

    assert [c.pk for c in plan.eligible] == [ready.pk]
    reasons = dict((c.pk, why) for c, why in plan.excluded)
    assert "меньше 7 дней" in reasons[fresh.pk]
    assert "дождитесь ночной сверки" in reasons[stale_check.pk]
    ready.refresh_from_db()
    assert ready.status == StaleProductCandidate.Status.HIDDEN
    product = ready.product
    product.refresh_from_db()
    assert product.is_active is False
    assert product.domain_item.is_active is False
    fresh.product.refresh_from_db()
    assert fresh.product.is_active is True


@pytest.mark.django_db
def test_keep_returns_hidden_product_to_site():
    candidate = _candidate(_product(1), hidden_days=1)

    keep_candidates([candidate.pk])

    candidate.refresh_from_db()
    candidate.product.refresh_from_db()
    assert candidate.status == StaleProductCandidate.Status.DISMISSED
    assert candidate.product.is_active is True


# --- лимиты и подозрительная база ---------------------------------------------------------


@pytest.mark.django_db
def test_more_than_per_action_limit_is_refused_entirely(settings):
    settings.STALE_PRODUCT_MAX_PER_ACTION = 2
    _catalog(20)
    candidates = [_candidate(_product(index)) for index in range(1, 4)]

    with pytest.raises(StaleProductsRefused, match="не больше 2"):
        hide_candidates([c.pk for c in candidates])

    assert not Product.objects.filter(pk__in=[c.product_id for c in candidates], is_active=False).exists()


@pytest.mark.django_db
def test_too_large_share_of_source_catalog_is_refused(settings):
    settings.STALE_PRODUCT_MAX_SOURCE_PERCENT = 10
    _catalog(8)
    candidates = [_candidate(_product(index)) for index in range(1, 3)]  # 2 из 10 = 20 %

    plan = plan_action(StaleProductCandidate.objects.select_related("product"), "hide")

    assert "больше 10 % каталога" in plan.refusal
    with pytest.raises(StaleProductsRefused):
        hide_candidates([c.pk for c in candidates])


@pytest.mark.django_db
def test_suspiciously_small_database_is_refused(settings):
    settings.STALE_PRODUCT_MIN_CATALOG_PRODUCTS = 1000
    candidate = _candidate(_product(1))

    plan = plan_action([candidate], "hide")

    assert "пустую или чужую базу" in plan.refusal


# --- шаг 2: удалить ------------------------------------------------------------------------


@pytest.mark.django_db
def test_delete_needs_hidden_long_enough_and_unprotected():
    _catalog(20)
    user = get_user_model().objects.create_user(username="owner", email="owner@example.com", password="x" * 20)
    not_hidden = _candidate(_product(1))
    hidden_recently = _candidate(_product(2), hidden_days=3)
    in_cart = _candidate(_product(3), hidden_days=20)
    CartItem.objects.create(cart=Cart.objects.create(session_key="s1"), product=in_cart.product, quantity=1, price=1)
    edited = _candidate(_product(4), hidden_days=20)
    LogEntry.objects.create(
        user=user, content_type=ContentType.objects.get_for_model(Product), object_id=str(edited.product_id),
        object_repr="x", action_flag=CHANGE,
    )
    ready = _candidate(_product(5), hidden_days=20)

    plan = plan_action(StaleProductCandidate.objects.select_related("product"), "delete")

    assert [c.pk for c in plan.eligible] == [ready.pk]
    reasons = dict((c.pk, why) for c, why in plan.excluded)
    assert reasons[not_hidden.pk] == "сначала скройте с сайта"
    assert "скрыт меньше 14 дней" in reasons[hidden_recently.pk]
    assert reasons[in_cart.pk] == "только скрыть: в Списке заявки покупателя"
    assert reasons[edited.pk] == "только скрыть: правили вручную в админке"


@pytest.mark.django_db
def test_product_found_again_at_seller_is_not_deleted():
    _catalog(20)
    candidate = _candidate(_product(1), hidden_days=20)
    gateway = FakeGateway({})

    result = delete_candidates([candidate.pk], gateway=gateway, recheck=lambda c: "present")

    assert Product.objects.filter(pk=candidate.product_id).exists()
    candidate.refresh_from_db()
    assert candidate.status == StaleProductCandidate.Status.RETURNED
    assert result["returned"] == [candidate.product.name]


@pytest.mark.django_db
def test_unconfirmed_recheck_does_not_delete():
    _catalog(20)
    candidate = _candidate(_product(1), hidden_days=20)

    result = delete_candidates([candidate.pk], gateway=FakeGateway({}), recheck=lambda c: "error")

    assert Product.objects.filter(pk=candidate.product_id).exists()
    assert result["skipped"] == [(candidate.product.name, "не удалось проверить у продавца")]


@pytest.mark.django_db
def test_delete_backs_up_and_removes_only_unshared_files(monkeypatch, django_capture_on_commit_callbacks):
    _catalog(20)
    shared, own = "products/lcw/shared.jpg", "products/lcw/own.jpg"
    product = _product(1, images=[own, shared])
    neighbour = _product(2, images=[shared])
    candidate = _candidate(product, hidden_days=20)
    gateway = FakeGateway({own: 1000, shared: 2000})
    signal_deletes = []
    monkeypatch.setattr(
        "apps.catalog.signals._delete_storage_key_if_unreferenced",
        lambda path, storage=None: signal_deletes.append(path),
    )

    with django_capture_on_commit_callbacks(execute=True):
        result = delete_candidates([candidate.pk], gateway=gateway, recheck=lambda c: "gone")

    assert not Product.objects.filter(pk=product.pk).exists()
    assert not ProductImage.objects.filter(product_id=product.pk).exists()
    assert Product.objects.filter(pk=neighbour.pk).exists()
    # Копия — до удаления, обоих файлов; удалён только свой, общий с соседом остался.
    assert gateway.backups == {own: 1000, shared: 2000}
    assert gateway.deleted == [own]
    assert signal_deletes == []
    log = ProductDeletionLog.objects.get(product_id=product.pk)
    assert log.files_deleted == 1 and log.bytes_freed == 1000
    assert {item["path"]: item["state"] for item in log.files} == {own: "deleted", shared: "shared"}
    assert log.objects_count > 3
    assert result["files_deleted"] == 1 and result["shared_kept"] == 1


@pytest.mark.django_db
def test_failed_backup_keeps_product_and_files():
    _catalog(20)
    own = "products/lcw/own.jpg"
    candidate = _candidate(_product(1, images=[own]), hidden_days=20)
    gateway = FakeGateway({own: 1000})
    gateway.fail_backup.add(own)

    result = delete_candidates([candidate.pk], gateway=gateway, recheck=lambda c: "gone")

    assert Product.objects.filter(pk=candidate.product_id).exists()
    assert gateway.deleted == []
    assert result["skipped"][0][1] == "ошибка: RuntimeError"
    assert not ProductDeletionLog.objects.exists()


@pytest.mark.django_db
def test_reference_check_failure_deletes_no_files(monkeypatch):
    _catalog(20)
    own = "products/lcw/own.jpg"
    candidate = _candidate(_product(1, images=[own]), hidden_days=20)
    gateway = FakeGateway({own: 1000})

    def broken(keys):
        raise MediaReferenceCheckError("catalog.ProductImage.image_file: timeout")

    monkeypatch.setattr(stale_products, "reference_counts", broken)

    result = delete_candidates([candidate.pk], gateway=gateway, recheck=lambda c: "gone")

    assert gateway.deleted == []
    assert "Проверка ссылок не прошла" in result["files_error"]
    assert gateway.backups == {own: 1000}


@pytest.mark.django_db
def test_deletion_waits_while_cleanup_orphaned_media_runs():
    _catalog(20)
    candidate = _candidate(_product(1), hidden_days=20)
    cache.add(stale_products.MEDIA_DELETE_LOCK_KEY, "cleanup", timeout=60)

    result = delete_candidates([candidate.pk], gateway=FakeGateway({}), recheck=lambda c: "gone")

    assert result == {"status": "busy"}
    assert Product.objects.filter(pk=candidate.product_id).exists()


@pytest.mark.django_db
def test_cleanup_orphaned_media_skips_while_products_are_deleted(settings):
    from apps.catalog.tasks import cleanup_orphaned_media

    settings.DEBUG = False
    cache.add(stale_products.MEDIA_DELETE_LOCK_KEY, "stale-products", timeout=60)

    assert cleanup_orphaned_media(dry_run=True)["reason"] == "media_delete_busy"


@pytest.mark.django_db
def test_restore_returns_rows_and_files():
    _catalog(20)
    own = "products/lcw/own.jpg"
    product = _product(1, images=[own])
    domain_type = type(product.domain_item)
    candidate = _candidate(product, hidden_days=20)
    gateway = FakeGateway({own: 1000})
    delete_candidates([candidate.pk], gateway=gateway, recheck=lambda c: "gone")
    log = ProductDeletionLog.objects.get(product_id=product.pk)

    failed = restore_deletion(log, gateway=gateway)

    assert failed == []
    restored = Product.objects.get(pk=product.pk)
    assert restored.is_active is False
    assert list(restored.images.values_list("image_file", flat=True)) == [own]
    assert isinstance(restored.domain_item, domain_type)
    assert restored.stale_candidate.status == StaleProductCandidate.Status.HIDDEN
    assert gateway.files == {own: 1000}
    log.refresh_from_db()
    assert log.status == ProductDeletionLog.Status.RESTORED
    with pytest.raises(StaleProductsRefused):
        restore_deletion(log, gateway=gateway)


@pytest.mark.django_db
def test_media_stats_count_only_files_nobody_else_uses():
    shared, own = "products/lcw/shared.jpg", "products/lcw/own.jpg"
    candidate = _candidate(_product(1, images=[own, shared]))
    _product(2, images=[shared])

    refresh_media_stats(gateway=FakeGateway({own: 1500, shared: 2000}))

    candidate.refresh_from_db()
    assert (candidate.files_total, candidate.files_to_free, candidate.bytes_to_free) == (2, 1, 1500)


# --- админка ------------------------------------------------------------------------------


@pytest.fixture
def admin_client_logged(client, settings):
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    user = get_user_model().objects.create_superuser(username="admin", email="admin@example.com", password="x" * 20)
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_admin_delete_action_shows_confirmation_then_queues_task(admin_client_logged, monkeypatch):
    _catalog(20)
    ready = _candidate(_product(1), hidden_days=20)
    fresh = _candidate(_product(2), hidden_days=2)
    queued = []
    monkeypatch.setattr(
        "apps.catalog.tasks.delete_stale_products_task.delay", lambda *args: queued.append(args)
    )
    url = "/admin/catalog/staleproductcandidate/"
    data = {"action": "delete_selected_forever", "_selected_action": [ready.pk, fresh.pk]}

    page = admin_client_logged.post(url, data)

    assert page.status_code == 200
    text = page.content.decode()
    assert "Удалить окончательно" in text and "Да, удалить 1 навсегда" in text
    assert "скрыт меньше 14 дней" in text
    assert queued == []

    admin_client_logged.post(url, {**data, "confirm": "yes"})
    assert queued[0][0] == [ready.pk]
    assert Product.objects.filter(pk=ready.product_id).exists()


@pytest.mark.django_db
def test_admin_pages_render(admin_client_logged):
    _candidate(_product(1))
    for url in (
        "/admin/catalog/staleproductcandidate/",
        "/admin/catalog/productdeletionlog/",
        "/admin/catalog/stockchecksourcestate/",
    ):
        assert admin_client_logged.get(url).status_code == 200
