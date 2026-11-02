"""IndexNow: сообщить Bing и Яндексу о новых, изменённых и снятых страницах товаров.

Устройство и включение — docs/INDEXNOW.md. Коротко: раз в час берём те же товары, что
секции sitemap products-<домен>, считаем в БД отпечаток значимых полей (название,
описание, наличие, переводы RU/EN — без цены: её пересчёт по курсу ежедневно трогает
почти весь каталог) и сравниваем с таблицей IndexNowUrlState. Новые, изменённые и
пропавшие с витрины страницы уходят POST-запросом, RU и EN-версия каждой.
"""
from __future__ import annotations

import logging

import requests
from django.apps import apps
from django.conf import settings
from django.db.models import OuterRef, Subquery, TextField, Value
from django.db.models.functions import MD5, Cast, Coalesce, Concat
from django.utils import timezone

from apps.catalog.models import AbstractDomainProduct, IndexNowUrlState, Product
from apps.catalog.querysets import non_public_shadow_product_q, source_variant_q
from apps.catalog.services.product_resolve import build_canonical_path

logger = logging.getLogger(__name__)

ENDPOINT = "https://api.indexnow.org/indexnow"
MAX_URLS_PER_REQUEST = 10_000  # предел протокола
URLS_PER_PATH = 2  # /product/... и /en/product/...
REQUEST_TIMEOUT_SECONDS = 30


def _domain_models() -> list[type[AbstractDomainProduct]]:
    return [
        model
        for model in apps.get_app_config("catalog").get_models()
        if issubclass(model, AbstractDomainProduct) and not model._meta.proxy
    ]


def _translation_hash(model, locale: str) -> Subquery:
    translation_model = model._meta.get_field("translations").related_model
    return Subquery(
        translation_model.objects.filter(product=OuterRef("pk"), locale=locale)
        .annotate(h=MD5(Concat("name", Value("|"), "description", output_field=TextField())))
        .values("h")[:1]
    )


def fingerprint_rows(model):
    """(slug, отпечаток) товаров модели, которые сейчас в sitemap.

    Отбор как у SitemapProductsView (активные, без копий вариантов и заглушек лекарств),
    но служебные строки исключаются подзапросом по частичным индексам (миграция 0217):
    условие на external_data в основном запросе детоастило бы дампы парсеров каждый час.
    """
    fingerprint = MD5(
        Concat(
            "name",
            Value("|"),
            "description",
            Value("|"),
            Cast("is_available", TextField()),
            Value("|"),
            Coalesce(_translation_hash(model, "ru"), Value(""), output_field=TextField()),
            Value("|"),
            Coalesce(_translation_hash(model, "en"), Value(""), output_field=TextField()),
            output_field=TextField(),
        )
    )
    return (
        model.objects.filter(is_active=True)
        .exclude(slug__isnull=True)
        .exclude(slug="")
        .exclude(id__in=model.objects.filter(source_variant_q()).values("id"))
        .exclude(base_product_id__in=Product.objects.filter(non_public_shadow_product_q()).values("id"))
        .annotate(fp=fingerprint)
        .values_list("slug", "fp")
    )


def current_fingerprints() -> dict[str, str]:
    """Путь страницы → отпечаток по всем доменам товаров."""
    result: dict[str, str] = {}
    for model in _domain_models():
        for slug, fp in fingerprint_rows(model).iterator(chunk_size=2000):
            result[build_canonical_path(model._domain_product_type, slug)] = fp
    return result


def _site_url() -> str:
    return settings.FRONTEND_SITE_URL.rstrip("/")


def _page_urls(path: str) -> list[str]:
    site = _site_url()
    return [f"{site}{path}", f"{site}/en{path}"]


def _post(urls: list[str]) -> int | None:
    """Код ответа IndexNow; None — сеть недоступна."""
    site = _site_url()
    key = settings.INDEXNOW_KEY
    payload = {
        "host": site.split("://", 1)[-1],
        "key": key,
        "keyLocation": f"{site}/{key}.txt",
        "urlList": urls,
    }
    try:
        response = requests.post(
            ENDPOINT,
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.warning("IndexNow: запрос не прошёл: %s", exc)
        return None
    if response.status_code in (200, 202):
        return response.status_code
    logger.warning(
        "IndexNow: ответ %s на %s URL: %s",
        response.status_code,
        len(urls),
        response.text[:500],
    )
    return response.status_code


def _sent_today_urls() -> int:
    day_start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return IndexNowUrlState.objects.filter(submitted_at__gte=day_start).count() * URLS_PER_PATH


def submit_changed_products() -> dict:
    """Отправить в IndexNow изменения с прошлого запуска. Ошибки ответа — в журнал."""
    if not getattr(settings, "INDEXNOW_ENABLED", False):
        return {"status": "disabled"}

    current = current_fingerprints()
    known = {
        path: (fp, is_public)
        for path, fp, is_public in IndexNowUrlState.objects.values_list("path", "fingerprint", "is_public")
    }

    if not known:
        # Первый запуск: запоминаем каталог как есть, иначе весь он ушёл бы «новым».
        IndexNowUrlState.objects.bulk_create(
            [IndexNowUrlState(path=path, fingerprint=fp) for path, fp in current.items()],
            batch_size=2000,
        )
        logger.info("IndexNow: первый запуск, запомнено %s страниц, ничего не отправлено", len(current))
        return {"status": "baseline", "pages": len(current)}

    new, changed, gone = [], [], []
    for path, fp in current.items():
        known_fp, is_public = known.get(path, ("", False))
        if not is_public:
            new.append((path, fp))
        elif known_fp != fp:
            changed.append((path, fp))
    for path, (_, is_public) in known.items():
        if is_public and path not in current:
            gone.append((path, ""))

    pending = new + gone + changed
    stats = {
        "status": "ok",
        "new": len(new),
        "changed": len(changed),
        "gone": len(gone),
        "submitted_urls": 0,
    }
    if not pending:
        return stats

    budget = settings.INDEXNOW_DAILY_URL_LIMIT - _sent_today_urls()
    allowed_paths = max(0, budget // URLS_PER_PATH)
    if allowed_paths < len(pending):
        stats["deferred_pages"] = len(pending) - allowed_paths
        pending = pending[:allowed_paths]
    if not pending:
        stats["status"] = "daily_limit"
        logger.info("IndexNow: дневной предел исчерпан, ждут %s страниц", stats["deferred_pages"])
        return stats

    paths_per_request = MAX_URLS_PER_REQUEST // URLS_PER_PATH
    for start in range(0, len(pending), paths_per_request):
        chunk = pending[start:start + paths_per_request]
        urls = [url for path, _ in chunk for url in _page_urls(path)]
        code = _post(urls)
        if code not in (200, 202):
            # 429 и прочие ошибки: остаток уйдёт при следующем запуске.
            stats["status"] = f"error_{code}" if code else "network_error"
            break
        now = timezone.now()
        IndexNowUrlState.objects.bulk_create(
            [
                IndexNowUrlState(path=path, fingerprint=fp, is_public=bool(fp), submitted_at=now)
                for path, fp in chunk
            ],
            batch_size=2000,
            update_conflicts=True,
            unique_fields=["path"],
            update_fields=["fingerprint", "is_public", "submitted_at"],
        )
        stats["submitted_urls"] += len(urls)

    logger.info("IndexNow: %s", stats)
    return stats
