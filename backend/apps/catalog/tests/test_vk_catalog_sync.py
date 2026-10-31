"""Синхронизация каталога ВК: HTTP подменён, настоящий API ВК не вызывается."""
import importlib
import io
import json
import logging
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
import requests
from celery.exceptions import SoftTimeLimitExceeded
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import CommandError, call_command
from PIL import Image

from apps.catalog import tasks
from apps.catalog.currency_models import GlobalCurrencySettings
from apps.catalog.models import Category, MedicineProduct, Product
from apps.catalog.models_vk import VKCategoryMapping
from apps.catalog.services import vk_catalog_sync, vk_market_sync
from apps.catalog.services.vk_catalog_sync import LOCK_KEY, _iter_offers, run_catalog_sync

TOKEN = "secret-user-token"
UPLOAD_URL = "https://upload.vk.example/market"
IMAGE_URL = "https://cdn.example/photo.jpg"
WRITE_METHODS = {
    "market.add",
    "market.edit",
    "market.delete",
    "market.getProductPhotoUploadServer",
    "market.saveProductPhoto",
}
CHANGELIST = "/admin/catalog/vkcategorymapping/"


def _image(size=(500, 500), image_format="JPEG") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, "white").save(out, image_format)
    return out.getvalue()


class FakeResponse:
    def __init__(self, payload=None, *, text="", content=b""):
        self.payload = payload
        self.text = text
        self.content = content

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeVK:
    """Сообщество ВК в памяти: отвечает как API, запоминает все запросы."""

    def __init__(self):
        self.items: dict[int, dict] = {}
        self.calls: list[tuple[str, dict]] = []
        self.urls: list[str] = []
        self.script: dict[str, list] = {}  # метод → ответы по очереди: dict ошибки или исключение
        self.image = _image()
        self.next_id = 1000

    def put(self, item_id: int, sku: str | None, *, title="Товар в ВК", description="Описание товара в ВК",
            price="10000", availability=0, **extra) -> None:
        self.items[item_id] = {
            "id": item_id,
            "sku": sku,
            "title": title,
            "description": description,
            "price": {"amount": price},
            "availability": availability,
            **extra,
        }

    def put_offer(self, item_id: int, offer, **overrides) -> None:
        """Товар ВК, полностью совпадающий с оффером фида."""
        fields = {
            "title": offer.name,
            "description": offer.description,
            "price": str(int(offer.price * 100)),
        }
        sku = overrides.pop("sku", offer.sku)
        self.put(item_id, sku, **{**fields, **overrides})

    def called(self, method: str) -> list[dict]:
        return [params for name, params in self.calls if name == method]

    def writes(self) -> list[tuple[str, dict]]:
        return [call for call in self.calls if call[0] in WRITE_METHODS or call[0] == "upload"]

    def get(self, url, **kwargs):
        self.urls.append(url)
        return FakeResponse(content=self.image)

    def post(self, url, data=None, files=None, timeout=None):
        self.urls.append(url)
        if url == UPLOAD_URL:
            self.calls.append(("upload", {"files": files}))
            return FakeResponse(text='{"photo":"x","server":1}')
        assert url.startswith(vk_market_sync.VK_API_URL), url
        method = url.rsplit("/", 1)[1]
        assert data["access_token"] == TOKEN
        params = {key: value for key, value in data.items() if key not in ("access_token", "v")}
        self.calls.append((method, params))
        script = self.script.get(method)
        if script:
            step = script.pop(0)
            if isinstance(step, Exception):
                raise step
            return FakeResponse({"error": step})
        return FakeResponse({"response": getattr(self, method.replace(".", "_"))(params)})

    def market_get(self, params):
        listed = [item for item in self.items.values() if not item.get("variant")]
        variants = [item for item in self.items.values() if item.get("variant")]
        offset, count = params["offset"], params["count"]
        response = {"count": len(listed), "items": listed[offset:offset + count]}
        if params.get("need_variants") and offset == 0:
            response["variants"] = variants
        return response

    def market_add(self, params):
        self.next_id += 1
        self.put(self.next_id, params["sku"], title=params["name"], description=params["description"],
                 price=str(int(Decimal(params["price"]) * 100)))
        return {"market_item_id": self.next_id}

    def market_edit(self, params):
        item = self.items[params["item_id"]]
        if "price" in params:
            item["price"] = {"amount": str(int(Decimal(params["price"]) * 100))}
        if "name" in params:
            item["title"] = params["name"]
        if "description" in params:
            item["description"] = params["description"]
        if "deleted" in params:
            item["availability"] = params["deleted"]
        return 1

    def market_delete(self, params):
        del self.items[params["item_id"]]
        return 1

    def market_getProductPhotoUploadServer(self, params):
        return {"upload_url": UPLOAD_URL}

    def market_saveProductPhoto(self, params):
        return {"photo_id": 777}


@pytest.fixture
def vk(monkeypatch, settings):
    fake = FakeVK()
    monkeypatch.setattr(vk_market_sync.requests, "post", fake.post)
    monkeypatch.setattr(vk_market_sync.requests, "get", fake.get)
    monkeypatch.setattr(vk_market_sync.time, "sleep", lambda seconds: None)
    settings.VK_USER_TOKEN = TOKEN
    settings.VK_GROUP_ID = 42
    settings.VK_SYNC_MAX_DELETE_SHARE = 0.3
    settings.FRONTEND_SITE_URL = "https://mudaroba.example"
    settings.SOURCE_OFFER_CATALOG_PROJECTION_ENABLED = False
    cache.delete(LOCK_KEY)
    return fake


@pytest.fixture
def catalog(db, monkeypatch):
    """Цены без настоящих курсов и наценок, категория ВК с ID."""
    from apps.catalog.utils.currency_converter import currency_converter

    monkeypatch.setattr(
        currency_converter, "convert_price",
        lambda amount, source, target, apply_margin=True: (amount, amount, amount),
    )
    monkeypatch.setattr(
        GlobalCurrencySettings, "load", lambda: SimpleNamespace(default_margin_percentage=Decimal("0"))
    )
    VKCategoryMapping.objects.update_or_create(
        product_type="perfumery", gender="", defaults={"vk_category_path": "Парфюмерия", "vk_category_id": 20093},
    )
    return Category.objects.create(name="Парфюмерия", slug=f"perfumery-{uuid4().hex[:8]}")


def _product(category, name="Духи с амброй", price="100", **fields) -> Product:
    product = Product.objects.create(
        name=name,
        slug=f"product-{uuid4().hex}",
        category=category,
        price=Decimal(price),
        currency="RUB",
        description="Стойкий аромат с нотами амбры и ванили",
        is_available=True,
    )
    # update — без сигнала, который скачивает внешние картинки.
    Product.objects.filter(pk=product.pk).update(
        product_type="perfumery", main_image=IMAGE_URL, **fields
    )
    return product


def _offers() -> dict:
    return {offer.sku: offer for offer in _iter_offers()}


def _in_sync(vk, *products) -> None:
    """Товары уже есть в ВК и совпадают с фидом."""
    offers = _offers()
    for index, product in enumerate(products, start=1):
        vk.put_offer(index, offers[str(product.id)])


# --- Режим по умолчанию ---


def test_default_run_reports_and_changes_nothing(vk, catalog):
    new = _product(catalog, name="Новые духи")
    changed = _product(catalog, name="Подорожавшие духи")
    offers = _offers()
    vk.put_offer(1, offers[str(changed.id)], price="5000")
    vk.put(2, "999999")
    vk.put(3, "888888")
    vk.put(4, "777777")
    vk.put(5, "666666")
    vk.put(6, "555555")
    vk.put_offer(7, offers[str(changed.id)], sku="111")  # совпадает по тексту, но другой артикул

    report = run_catalog_sync(max_delete_share=1)

    assert vk.writes() == []
    assert {name for name, _ in vk.calls} == {"market.get"}
    assert report.add == [str(new.id)]
    assert report.update_stock == [str(changed.id)]
    assert len(report.delete) == 6
    text = report.text()
    assert "только отчёт" in text
    assert "добавит 1" in text and "удалит 6" in text
    assert "Новые духи" in text
    assert "цена 50 → " in text


def test_command_writes_only_with_apply_flag(vk, catalog):
    _product(catalog)
    out = io.StringIO()

    call_command("sync_vk_catalog", stdout=out)

    assert vk.writes() == []
    assert "добавит 1" in out.getvalue()

    call_command("sync_vk_catalog", apply=True, stdout=out)

    assert len(vk.called("market.add")) == 1
    assert "добавлено 1 из 1" in out.getvalue()


def test_command_rejects_share_outside_range(vk):
    with pytest.raises(CommandError):
        call_command("sync_vk_catalog", max_delete_share=30)


def test_missing_token_stops_before_any_request(vk, settings):
    settings.VK_USER_TOKEN = ""

    report = run_catalog_sync(apply=True)

    assert "VK_USER_TOKEN" in report.stop_reason
    assert vk.calls == []


# --- Настоящий запуск ---


def test_apply_adds_updates_and_deletes_by_sku(vk, catalog):
    new = _product(catalog, name="Новые духи")
    stale = _product(catalog, name="Новое название духов")
    same = _product(catalog, name="Духи без изменений")
    offers = _offers()
    vk.put_offer(1, offers[str(stale.id)], price="1", title="Старое название")
    vk.put_offer(2, offers[str(same.id)])
    vk.put(3, "999999")

    report = run_catalog_sync(apply=True, max_delete_share=0.5)

    assert report.stop_reason == ""
    assert (report.added, report.updated, report.deleted) == (1, 1, 1)
    offer = offers[str(new.id)]
    assert vk.called("market.add") == [{
        "owner_id": -42,
        "name": offer.name,
        "description": offer.description,
        "category_id": 20093,
        "price": str(offer.price),
        "main_photo_id": 777,
        "sku": str(new.id),
    }]
    edit = vk.called("market.edit")[0]
    assert edit["item_id"] == 1
    assert edit["name"] == offers[str(stale.id)].name
    assert edit["price"] == str(offers[str(stale.id)].price)
    assert "description" not in edit  # только то, что расходится
    assert vk.called("market.delete") == [{"owner_id": -42, "item_id": 3}]
    assert 2 not in {call["item_id"] for call in vk.called("market.edit")}


def test_second_run_finds_nothing_to_do(vk, catalog):
    _product(catalog)
    run_catalog_sync(apply=True)
    vk.calls.clear()

    report = run_catalog_sync(apply=True)

    assert vk.writes() == []
    assert report.summary().endswith("добавлено 0 из 0, обновлено 0 из 0, удалено 0 из 0, ошибок 0")


def test_text_formatting_differences_are_not_updates(vk, catalog):
    product = _product(catalog)
    offer = _offers()[str(product.id)]
    vk.put_offer(1, offer, description=offer.description.replace("\n", "<br>  "))

    report = run_catalog_sync()

    assert report.update_text == []


def test_price_and_availability_go_before_texts(vk, catalog):
    text_only = _product(catalog)
    price = _product(catalog)
    offers = _offers()
    vk.put_offer(1, offers[str(text_only.id)], title="Старое название")
    vk.put_offer(2, offers[str(price.id)], price="1")

    run_catalog_sync(apply=True)

    assert [call["item_id"] for call in vk.called("market.edit")] == [2, 1]


def test_hidden_card_from_feed_is_restored_not_added_again(vk, catalog):
    product = _product(catalog)
    vk.put_offer(1, _offers()[str(product.id)], availability=1)

    report = run_catalog_sync(apply=True)

    assert vk.called("market.add") == []
    assert vk.called("market.edit") == [{"owner_id": -42, "item_id": 1, "deleted": 0}]
    assert report.updated == 1


def test_variants_listed_apart_are_not_added_again(vk, catalog):
    product = _product(catalog)
    vk.put_offer(1, _offers()[str(product.id)], variant=True)

    report = run_catalog_sync()

    assert report.add == []
    assert report.delete == []


def test_market_get_reads_every_page(vk):
    for item_id in range(1, 451):
        vk.put(item_id, str(item_id))
    client = vk_market_sync.VKMarketSync(token=TOKEN, group_id=42)

    assert len(list(client.iter_market_items(include_hidden=True))) == 450
    assert len(vk.called("market.get")) == 3
    assert vk.called("market.get")[0]["with_disabled"] == 1


def test_incomplete_vk_listing_stops_the_run(vk, catalog, monkeypatch):
    _product(catalog)
    vk.put(1, "999999")
    monkeypatch.setattr(vk, "market_get", lambda params: {"count": 5, "items": []})

    report = run_catalog_sync(apply=True)

    assert "каталог ВК не прочитан" in report.stop_reason
    assert vk.writes() == []


# --- Предохранители ---


def test_large_delete_share_stops_the_run(vk, catalog):
    product = _product(catalog)
    _in_sync(vk, product)
    vk.put(2, "999999")
    vk.put(3, "888888")

    report = run_catalog_sync(apply=True)

    assert "на удаление попало 2 из 3" in report.stop_reason
    assert vk.writes() == []


def test_delete_share_can_be_raised_for_one_run(vk, catalog):
    product = _product(catalog)
    _in_sync(vk, product)
    vk.put(2, "999999")
    vk.put(3, "888888")

    report = run_catalog_sync(apply=True, max_delete_share=0.7)

    assert report.deleted == 2


def test_empty_feed_deletes_nothing(vk, catalog):
    vk.put(1, "999999")

    report = run_catalog_sync(apply=True, max_delete_share=1)

    assert report.stop_reason == "фид пустой, ничего не меняем"
    assert vk.writes() == []


def test_feed_failure_deletes_nothing(vk, catalog, monkeypatch):
    _product(catalog)
    vk.put(1, "999999")

    def broken_feed():
        yield from ()
        raise RuntimeError("база недоступна")

    monkeypatch.setattr(vk_catalog_sync, "iter_feed_offers", broken_feed)

    report = run_catalog_sync(apply=True, max_delete_share=1)

    assert report.stop_reason == "фид не собрался, ничего не меняем"
    assert vk.writes() == []


def test_cards_without_our_sku_are_kept_and_reported(vk, catalog):
    products = [_product(catalog) for _ in range(3)]
    _in_sync(vk, *products)
    vk.put(10, "", title="Сертификат")
    vk.put(11, "ABC-1", title="Чужой артикул")

    report = run_catalog_sync(apply=True, max_delete_share=0.45)

    assert vk.called("market.delete") == []
    assert {item.id for item in report.foreign} == {10, 11}
    assert "Без нашего артикула: 2" in report.text()
    assert "Сертификат" in report.text()


def test_mostly_foreign_catalog_stops_instead_of_duplicating(vk, catalog):
    """Если ВК не отдаёт артикул, весь каталог выглядел бы новым и получил бы дубли."""
    product = _product(catalog)
    vk.put_offer(1, _offers()[str(product.id)], sku=None)

    report = run_catalog_sync(apply=True)

    assert "без нашего артикула 1 из 1" in report.stop_reason
    assert vk.writes() == []


def test_duplicate_sku_is_left_for_the_owner(vk, catalog):
    product = _product(catalog)
    offer = _offers()[str(product.id)]
    vk.put_offer(1, offer)
    vk.put_offer(2, offer)

    report = run_catalog_sync(apply=True, max_delete_share=1)

    assert vk.called("market.delete") == []
    assert [item.id for item in report.duplicates] == [2]
    assert "Дубли артикула: 1" in report.text()


def test_medicines_and_import_restricted_are_not_uploaded_and_their_cards_are_removed(vk, catalog):
    allowed = _product(catalog)
    root, _ = Category.objects.get_or_create(slug="medicines", defaults={"name": "Медицина"})
    medicine = Product.objects.create(
        name="Лекарство", slug=f"medicine-{uuid4().hex}", product_type="medicines", category=root, is_active=True
    )
    restricted = _product(catalog, name="Ввоз ограничен")
    MedicineProduct.objects.bulk_create([
        MedicineProduct(
            base_product=restricted,
            name=restricted.name,
            slug=restricted.slug,
            category=catalog,
            import_restricted_countries="RU",
        )
    ])
    _in_sync(vk, allowed)
    for item_id, sku in enumerate((medicine.id, restricted.id), start=2):
        vk.put(item_id, str(sku))

    report = run_catalog_sync(apply=True, max_delete_share=0.7)

    assert report.add == []
    assert {call["item_id"] for call in vk.called("market.delete")} == {2, 3}


def test_offer_without_category_id_is_reported_not_added(vk, catalog):
    product = _product(catalog)
    VKCategoryMapping.objects.filter(product_type="perfumery", gender="").update(vk_category_id=None)

    report = run_catalog_sync(apply=True)

    assert vk.called("market.add") == []
    assert report.skipped == {vk_catalog_sync.SKIP_NO_CATEGORY: [str(product.id)]}


# --- Сбои и продолжение ---


def test_rate_limit_is_retried(vk, catalog):
    product = _product(catalog)
    vk.put_offer(1, _offers()[str(product.id)], price="1")
    vk.script["market.edit"] = [{"error_code": 6, "error_msg": "Too many requests per second"}]

    report = run_catalog_sync(apply=True)

    assert len(vk.called("market.edit")) == 2
    assert report.updated == 1


def test_network_failure_is_retried(vk, catalog):
    product = _product(catalog)
    vk.put_offer(1, _offers()[str(product.id)], price="1")
    vk.script["market.edit"] = [requests.ConnectionError("нет сети")]

    report = run_catalog_sync(apply=True)

    assert report.updated == 1


def test_add_is_not_repeated_after_timeout(vk, catalog):
    """После таймаута товар мог создаться: повтор дал бы дубль, увидит следующий запуск."""
    _product(catalog)
    vk.script["market.add"] = [requests.Timeout("таймаут")]

    report = run_catalog_sync(apply=True)

    assert len(vk.called("market.add")) == 1
    assert report.errors == 1


def test_one_failed_item_does_not_stop_the_run(vk, catalog):
    first, second = _product(catalog), _product(catalog)
    offers = _offers()
    vk.put_offer(1, offers[str(first.id)], price="1")
    vk.put_offer(2, offers[str(second.id)], price="1")
    vk.script["market.edit"] = [{"error_code": 1408, "error_msg": "Item has bad links in description"}]

    report = run_catalog_sync(apply=True)

    assert (report.updated, report.errors) == (1, 1)
    assert "1408" in report.text()


def test_auth_error_stops_the_run_and_next_run_continues(vk, catalog):
    first, second = _product(catalog), _product(catalog)
    offers = _offers()
    vk.put_offer(1, offers[str(first.id)], price="1")
    vk.put_offer(2, offers[str(second.id)], price="1")
    original_edit = vk.market_edit

    def fail_second(params):
        vk.market_edit = original_edit
        original_edit(params)
        vk.script["market.edit"] = [{"error_code": 5, "error_msg": "User authorization failed"}]
        return 1

    vk.market_edit = fail_second

    report = run_catalog_sync(apply=True)

    assert report.updated == 1
    assert "следующий запуск продолжит" in report.stop_reason

    vk.calls.clear()
    report = run_catalog_sync(apply=True)

    assert report.stop_reason == ""
    assert [call["item_id"] for call in vk.called("market.edit")] == [2]


def test_flood_control_stops_after_retries(vk, catalog):
    first, second = _product(catalog), _product(catalog)
    offers = _offers()
    vk.put_offer(1, offers[str(first.id)], price="1")
    vk.put_offer(2, offers[str(second.id)], price="1")
    vk.script["market.edit"] = [{"error_code": 9, "error_msg": "Flood control"}] * 4

    report = run_catalog_sync(apply=True)

    assert len(vk.called("market.edit")) == 4
    assert "Flood control" in report.stop_reason


def test_many_errors_in_a_row_stop_the_run(vk, catalog, monkeypatch):
    monkeypatch.setattr(vk_catalog_sync, "MAX_CONSECUTIVE_ERRORS", 2)
    products = [_product(catalog) for _ in range(3)]
    offers = _offers()
    for index, product in enumerate(products, start=1):
        vk.put_offer(index, offers[str(product.id)], price="1")
    vk.script["market.edit"] = [{"error_code": 100, "error_msg": "One of the parameters"}] * 3

    report = run_catalog_sync(apply=True)

    assert len(vk.called("market.edit")) == 2
    assert "2 ошибок API подряд" in report.stop_reason


def test_broken_photo_skips_only_that_product(vk, catalog, monkeypatch):
    _product(catalog)
    _product(catalog)
    images = iter([b"not an image", _image()])
    monkeypatch.setattr(
        vk_market_sync.requests, "get", lambda url, **kwargs: FakeResponse(content=next(images))
    )

    report = run_catalog_sync(apply=True)

    assert (report.added, report.errors) == (1, 1)
    assert "фото не скачалось" in report.text()


def test_task_time_limit_gives_a_partial_report(vk, catalog, monkeypatch):
    _product(catalog)

    def out_of_time(*args, **kwargs):
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(vk_market_sync.VKMarketSync, "add_item", out_of_time)

    report = run_catalog_sync(apply=True)

    assert "закончилось время" in report.stop_reason
    assert cache.add(LOCK_KEY, True, timeout=1)  # блокировка снята


def test_second_apply_does_not_run_alongside_the_first(vk, catalog):
    vk.put(1, "999999")
    cache.add(LOCK_KEY, True, timeout=60)

    report = run_catalog_sync(apply=True, max_delete_share=1)

    assert report.stop_reason == "предыдущий запуск ещё идёт"
    assert vk.calls == []
    cache.delete(LOCK_KEY)


# --- Токен ---


def test_token_never_reaches_logs_urls_or_report(vk, catalog, caplog):
    first, second = _product(catalog), _product(catalog)
    offers = _offers()
    vk.put_offer(1, offers[str(first.id)], price="1")
    vk.put_offer(2, offers[str(second.id)], price="1")
    vk.script["market.edit"] = [
        requests.ConnectionError(f"https://api.vk.ru/method?access_token={TOKEN}"),
        {"error_code": 100, "error_msg": f"bad token {TOKEN}"},
    ]

    with caplog.at_level(logging.DEBUG):
        report = run_catalog_sync(apply=True)

    assert report.errors == 1
    assert TOKEN not in caplog.text
    assert TOKEN not in report.text()
    assert all(TOKEN not in url for url in vk.urls)


def test_token_is_not_in_listing_error(vk, catalog):
    _product(catalog)
    vk.script["market.get"] = [{"error_code": 5, "error_msg": f"invalid access_token {TOKEN}"}]

    report = run_catalog_sync()

    assert "[5]" in report.stop_reason
    assert TOKEN not in report.stop_reason


# --- Фото ---


def test_webp_is_converted_for_vk(vk):
    vk.image = _image(image_format="WEBP")
    client = vk_market_sync.VKMarketSync(token=TOKEN, group_id=42)

    assert client.upload_main_photo(IMAGE_URL) == 777

    filename, content = vk.called("upload")[0]["files"]["file"]
    assert filename == "photo.jpg"
    assert Image.open(content).format == "JPEG"
    assert json.loads(vk.called("market.saveProductPhoto")[0]["upload_response"])["server"] == 1


def test_small_photo_is_rejected_before_upload(vk):
    vk.image = _image(size=(300, 300))
    client = vk_market_sync.VKMarketSync(token=TOKEN, group_id=42)

    with pytest.raises(vk_market_sync.VKPhotoError):
        client.upload_main_photo(IMAGE_URL)

    assert vk.calls == []


# --- Задача, расписание, админка, миграция ---


def test_schedule_does_nothing_while_disabled(vk, settings, monkeypatch):
    settings.VK_SYNC_ENABLED = False
    sent = []
    monkeypatch.setattr("apps.monitoring.watchdog.send_admin_telegram_notification", sent.append)

    assert "выключено" in tasks.sync_vk_catalog_task(apply=True, scheduled=True)
    assert vk.calls == []
    assert sent == []


def test_schedule_entry_is_a_real_run_guarded_by_the_setting():
    from django.conf import settings

    assert settings.VK_SYNC_ENABLED is False
    entry = settings.CELERY_BEAT_SCHEDULE["catalog-sync-vk-catalog"]
    assert entry["task"] == "catalog.sync_vk_catalog"
    assert entry["kwargs"] == {"apply": True, "scheduled": True}


def test_enabled_schedule_syncs_and_reports_to_telegram(vk, catalog, settings, monkeypatch):
    settings.VK_SYNC_ENABLED = True
    _product(catalog)
    sent = []
    monkeypatch.setattr("apps.monitoring.watchdog.send_admin_telegram_notification", sent.append)

    tasks.sync_vk_catalog_task(apply=True, scheduled=True)

    assert len(vk.called("market.add")) == 1
    assert "добавлено 1 из 1" in sent[0]


def test_manual_task_is_report_only_by_default(vk, catalog, monkeypatch):
    _product(catalog)
    sent = []
    monkeypatch.setattr("apps.monitoring.watchdog.send_admin_telegram_notification", sent.append)

    tasks.sync_vk_catalog_task()

    assert vk.writes() == []
    assert "только отчёт" in sent[0]


@pytest.fixture
def queued(monkeypatch):
    calls = []
    monkeypatch.setattr(tasks.sync_vk_catalog_task, "delay", lambda **kwargs: calls.append(kwargs))
    return calls


def _login(client, *, superuser: bool):
    user = get_user_model().objects.create_user(
        username=f"staff-{uuid4().hex[:6]}",
        email=f"{uuid4().hex[:6]}@example.com",
        password="x" * 20,
        is_staff=True,
        is_superuser=superuser,
    )
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_admin_apply_is_superuser_only(client, queued):
    _login(client, superuser=False)

    response = client.post(f"{CHANGELIST}sync-catalog/apply/")

    assert response.status_code == 302
    assert queued == []

    _login(client, superuser=True)
    client.get(f"{CHANGELIST}sync-catalog/apply/")
    assert queued == []

    client.post(f"{CHANGELIST}sync-catalog/apply/")
    assert queued == [{"apply": True}]


@pytest.mark.django_db
def test_admin_report_is_available_to_staff_and_read_only(client, queued):
    _login(client, superuser=False)

    client.post(f"{CHANGELIST}sync-catalog/report/")

    assert queued == [{}]


@pytest.mark.django_db
def test_admin_shows_apply_button_to_superuser(client, settings):
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    _login(client, superuser=True)

    assert "sync-catalog/apply/" in client.get(CHANGELIST).content.decode()


@pytest.mark.django_db
def test_migration_fills_category_ids_by_path():
    from django.apps import apps as django_apps

    migration = importlib.import_module("apps.catalog.migrations.0232_vk_category_id")
    rows = {
        ("shoes", "men"): ("Гардероб > Мужчинам > Обувь", 20001),
        ("clothing", "women"): ("Гардероб > Женщинам", 20000),
        ("furniture", ""): ("Дом и дача > Мебель", 20026),
        ("books", ""): ("Изменённый в админке путь", None),
    }
    for (product_type, gender), (path, _) in rows.items():
        VKCategoryMapping.objects.update_or_create(
            product_type=product_type, gender=gender,
            defaults={"vk_category_path": path, "vk_category_id": None},
        )

    migration.fill_category_ids(django_apps, None)

    for (product_type, gender), (_, expected) in rows.items():
        row = VKCategoryMapping.objects.get(product_type=product_type, gender=gender)
        assert row.vk_category_id == expected
