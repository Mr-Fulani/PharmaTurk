"""Ночная сверка наличия у продавцов (docs/NIGHTLY_STOCK_CHECK.md).

Каждую ночь короткие пачки (Celery Beat раз в 10 минут, 01:00–06:30 МСК)
открывают карточки товаров, которые у нас «в наличии», тем же путём, что и
обновление карточки при открытии (``ProductCardSourceRefreshService``): цена,
наличие, цвета и размеры, предложения источника. Тексты, медиа и SEO не меняются.

Только бесплатные источники. Пропавший у продавца товар (страница 404) не
снимается с продажи разом, а становится кандидатом ``StaleProductCandidate`` —
удаляет его только владелец в админке.

Предохранители: окно тихих часов, лимит карточек в минуту на сайт, одна пачка за
раз (блокировка), источник пропускается, пока идёт его обход парсером,
10 временных ошибок подряд — сайт до следующей ночи не трогаем, слишком много
пропаж за ночь — пауза источника до решения человека и тревога в Telegram.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime
from typing import Any, Callable
from urllib.parse import urlparse

import httpx
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from apps.catalog.models import Product
from apps.catalog.models_stock import SOURCE_TITLES, StaleProductCandidate, StockCheckSourceState
from apps.catalog.services.product_card_source_refresh import (
    ProductCardRefreshError,
    ProductCardSourceRefreshService,
    RefreshTarget,
)
from apps.catalog.services.source_offer_verification import SourceOfferVerificationService
from apps.http_errors import PaidAccessUnavailableError
from apps.scrapers.base.offers import OfferGone, OfferNotFound

logger = logging.getLogger(__name__)

BATCH_LOCK_KEY = "nightly-stock-check:batch:v1"
# Временные сбои: сайт не ответил, лимит запросов, внутренняя ошибка.
RETRYABLE_CODES = frozenset({"source_unavailable", "rate_limited", "internal_error"})
STAT_KEYS = (
    "checked",
    "lost",
    "became_unavailable",
    "became_available",
    "price_changed",
    "gone",
    "new_candidates",
    "errors",
    "rejected",
)


def _setting_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def nightly_sources() -> list[str]:
    """Источники ночной сверки без платных (FLO, Zara/Inditex, Akakçe — только с решения владельца)."""
    paid = {str(key).strip().casefold() for key in getattr(settings, "NIGHTLY_STOCK_CHECK_PAID_SOURCES", [])}
    sources = []
    for key in getattr(settings, "NIGHTLY_STOCK_CHECK_SOURCES", []) or []:
        key = str(key or "").strip().casefold()
        if key and key not in paid and key not in sources:
            sources.append(key)
    return sources


def source_rate_per_minute(parser_key: str) -> int:
    rates = getattr(settings, "NIGHTLY_STOCK_CHECK_RATE_PER_MINUTE", {}) or {}
    try:
        value = int(rates.get(parser_key, rates.get("default", 6)))
    except (TypeError, ValueError, AttributeError):
        value = 6
    return max(1, min(value, 60))


def _parse_time(value: str, default: str):
    try:
        return datetime.strptime(str(value or default), "%H:%M").time()
    except ValueError:
        return datetime.strptime(default, "%H:%M").time()


def window_end(now: datetime) -> datetime | None:
    """Конец тихих часов этой ночи или None, если сейчас не тихие часы."""
    local = timezone.localtime(now)
    start = _parse_time(getattr(settings, "NIGHTLY_STOCK_CHECK_START", "01:00"), "01:00")
    end = _parse_time(getattr(settings, "NIGHTLY_STOCK_CHECK_END", "06:30"), "06:30")
    if not start <= local.time() < end:
        return None
    return local.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)


def checkable_products(parser_key: str):
    """Что сверяем ночью: товары источника «в наличии» и кандидаты (подтвердить пропажу).

    Товары «нет в наличии» ночью не открываются: их возвращает обновление при
    открытии карточки. Лекарства — отдельный справочный контур.
    """
    return (
        Product.objects.filter(
            is_active=True,
            source_offers__parser_key=parser_key,
            source_offers__is_active=True,
        )
        .filter(Q(is_available=True) | Q(stale_candidate__status=StaleProductCandidate.Status.CANDIDATE))
        .exclude(product_type="medicines")
        .distinct()
    )


def source_scrape_running(parser_key: str) -> bool:
    """Идёт обход этого источника парсером — два обхода одного сайта сразу не нужны."""
    from apps.scrapers.models import SiteScraperTask

    return SiteScraperTask.objects.filter(
        status="running", scraper_config__parser_class__iexact=parser_key
    ).exists()


def mark_stale_candidate(product: Product, *, parser_key: str, source_url: str, now=None) -> bool:
    """Отмечает пропажу у продавца. True — товар стал кандидатом впервые (или снова)."""
    now = now or timezone.now()
    candidate = StaleProductCandidate.objects.filter(product=product).first()
    if candidate is None:
        StaleProductCandidate.objects.create(
            product=product,
            parser_key=parser_key,
            source_url=source_url,
            first_seen_at=now,
            last_gone_at=now,
        )
        return True
    if candidate.status == StaleProductCandidate.Status.RETURNED:
        # Товар возвращался к продавцу и снова пропал — срок считается заново.
        candidate.status = StaleProductCandidate.Status.HIDDEN if candidate.hidden_at else (
            StaleProductCandidate.Status.CANDIDATE
        )
        candidate.first_seen_at = now
        candidate.gone_checks = 0
    candidate.last_gone_at = now
    candidate.gone_checks += 1
    candidate.source_url = source_url
    candidate.save(update_fields=["status", "first_seen_at", "last_gone_at", "gone_checks", "source_url", "updated_at"])
    return False


def clear_stale_candidate(product_id: int) -> None:
    """Продавец снова показывает товар: кандидат снимается, скрытый — «снова есть у продавца»."""
    candidate = StaleProductCandidate.objects.filter(product_id=product_id).first()
    if candidate is None or candidate.status in (
        StaleProductCandidate.Status.DISMISSED,
        StaleProductCandidate.Status.RETURNED,
    ):
        return
    if candidate.status == StaleProductCandidate.Status.HIDDEN:
        candidate.status = StaleProductCandidate.Status.RETURNED
        candidate.save(update_fields=["status", "updated_at"])
        return
    candidate.delete()


class NightlyStockCheckService(ProductCardSourceRefreshService):
    """Обновление карточки для ночной сверки: только бесплатные источники, пропажа — кандидат."""

    @staticmethod
    def enabled() -> bool:
        return bool(getattr(settings, "NIGHTLY_STOCK_CHECK_ENABLED", False))

    @staticmethod
    def _allowed_sources() -> set[str]:
        return set(nightly_sources())

    @classmethod
    def _terminal_failure(cls, target: RefreshTarget) -> dict[str, Any] | None:
        # Пропажу проверяем каждую ночь: кандидат держится, только пока продавец не вернул товар.
        return None

    def _fetch_product(self, target: RefreshTarget):
        config = self._scraper_config(target.offer)
        if config is not None and config.use_proxy:
            # Платный прокси — только по отдельному решению владельца (docs/PAID_WEB_ACCESS_SERVICES.md).
            raise ProductCardRefreshError(
                "paid_access_unavailable", "Source requires a paid proxy", retryable=False
            )
        try:
            return super()._fetch_product(target)
        except ProductCardRefreshError as exc:
            if exc.code != "source_unavailable":
                raise
            failure = exc
        except PaidAccessUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 — ниже уточняем, пропал ли товар
            failure = exc
        # Полный парсер прячет пропажу в «карточки нет»: _make_request на 404 делает break,
        # UmmaLand глушит ошибки, LCW с пропавшего товара редиректит на главную (200).
        if self._source_says_gone(target):
            raise ProductCardRefreshError(
                "source_not_found", "Supplier product was not found", retryable=False
            ) from failure
        raise failure

    def _validated_snapshots(self, target: RefreshTarget, scraped):
        try:
            return super()._validated_snapshots(target, scraped)
        except ProductCardRefreshError as exc:
            # LCW «разбирает» и главную, куда увёл пропавший товар: ответ без цены и
            # вариантов не проходит проверку. Это пропажа, если продавец так и говорит.
            if exc.code in ("invalid_payload", "identity_mismatch", "invalid_source") and self._source_says_gone(target):
                raise ProductCardRefreshError(
                    "source_not_found", "Supplier product was not found", retryable=False
                ) from exc
            raise

    def _probe_parser(self, target: RefreshTarget):
        config = self._scraper_config(target.offer)
        parser = target.parser_class(
            base_url=config.base_url if config else f"https://{urlparse(target.offer.canonical_url).netloc}",
            timeout=self._request_timeout(target.parser_key),
            max_retries=0,
            use_proxy=False,
            username=config.scraper_username if config else "",
        )
        if config is not None:
            parser.configure_request_identity(
                user_agent=config.user_agent, headers=config.headers, cookies=config.cookies,
            )
        return parser

    def _source_says_gone(self, target: RefreshTarget) -> bool:
        """Товара у продавца точно нет: 404/410 или редирект со страницы товара на не-товар.

        Таймаут, 403/429/5xx, непонятная страница — «не знаем», не пропажа.
        """
        url = target.offer.canonical_url
        try:
            with self._probe_parser(target) as parser:
                # Сначала сама страница: 404/410 или редирект на главную/категорию (так делает LCW).
                try:
                    _html, final_url = parser._make_offer_request(url, include_final_url=True)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code in (404, 410):
                        return True
                else:
                    if _redirected_off_product(parser, url, final_url):
                        return True
                # Страница на месте — спросить лёгкую проверку источника (IKEA — артикул в API).
                try:
                    parser.check_offer(SourceOfferVerificationService._context(target.offer))
                except (OfferNotFound, OfferGone):
                    return True
                except Exception:  # noqa: BLE001 — не уверены — не пропажа
                    return False
                return False
        except Exception:  # noqa: BLE001 — сеть, блокировка: не уверены — не пропажа
            logger.info("nightly_stock_gone_probe_failed", exc_info=True, extra={"url": url})
            return False

    def _on_source_not_found(self, target: RefreshTarget) -> dict[str, int]:
        other_url = (
            target.product.source_offers.filter(is_active=True)
            .exclude(parser_key=target.parser_key, canonical_url=target.offer.canonical_url)
            .exists()
        )
        if other_url:
            # Пропал один цвет из нескольких: снимаем только его, как карточка.
            return self._mark_source_url_unavailable(target)
        changes = {"new_candidate": int(
            mark_stale_candidate(
                target.product, parser_key=target.parser_key, source_url=target.offer.canonical_url
            )
        )}
        if getattr(settings, "SCRAPER_GONE_REQUIRES_REVIEW", False):
            return changes
        return {**self._mark_source_url_unavailable(target), **changes}


def _redirected_off_product(parser, requested_url: str, final_url: str) -> bool:
    """Продавец увёл со страницы товара туда, где товара нет (главная, категория)."""
    requested = (urlparse(requested_url).path or "/").rstrip("/")
    final = (urlparse(final_url).path or "/").rstrip("/")
    if final == requested:
        return False
    if not final:
        return True
    for name in ("_is_product_url", "is_product_url", "is_lcw_product_url", "is_ikea_product_url"):
        check = getattr(parser, name, None)
        if callable(check):
            return not check(final_url)
    return False


def _reset_night(state: StockCheckSourceState, night) -> None:
    if state.night == night:
        return
    state.night = night
    state.stats = {key: 0 for key in STAT_KEYS}
    state.catalog_size = checkable_products(state.parser_key).count()
    state.save(update_fields=["night", "stats", "catalog_size", "updated_at"])


def _next_product_ids(parser_key: str, cursor_pk: int, limit: int = 50) -> list[int]:
    return list(
        checkable_products(parser_key)
        .filter(pk__gt=cursor_pk)
        .order_by("pk")
        .values_list("pk", flat=True)[:limit]
    )


def _alert(text: str) -> None:
    from apps.monitoring.watchdog import send_admin_telegram_notification

    send_admin_telegram_notification(text)


def _record(state: StockCheckSourceState, product_id: int, before: tuple, result: dict[str, Any]) -> str:
    """Записывает итог одной проверки в счётчики ночи; возвращает код исхода."""
    stats = state.stats
    for key in STAT_KEYS:
        stats.setdefault(key, 0)
    after = Product.objects.filter(pk=product_id).values_list("is_available", "price").first() or before
    status = result.get("status")
    code = str(result.get("error_code") or "")
    changes = result.get("changes") or {}
    if status == "succeeded":
        outcome = "ok"
        clear_stale_candidate(product_id)
    elif code == "source_not_found":
        outcome = "gone"
        stats["gone"] += 1
        stats["new_candidates"] += int(changes.get("new_candidate", 0))
    elif code in RETRYABLE_CODES:
        stats["errors"] += 1
        return "retryable"
    elif status == "not_eligible":
        return "skipped"
    else:
        # Другой товар в ответе, аномальная цена, неполный ответ — карточка не тронута.
        stats["rejected"] += 1
        return code or "rejected"
    stats["checked"] += 1
    if before[0] and (not after[0] or outcome == "gone"):
        # Был «в наличии», а у продавца закончился или пропал.
        stats["lost"] += 1
    if before[0] and not after[0]:
        stats["became_unavailable"] += 1
    elif not before[0] and after[0]:
        stats["became_available"] += 1
    if before[1] != after[1]:
        stats["price_changed"] += 1
    return outcome


def _loss_tripped(stats: dict) -> bool:
    """Слишком много товаров пропало за ночь — похоже на сбой парсера, а не на продавца."""
    sample = _setting_int("NIGHTLY_STOCK_CHECK_MIN_SAMPLE", 30, minimum=5, maximum=10000)
    share = float(getattr(settings, "NIGHTLY_STOCK_CHECK_MAX_LOSS_SHARE", 0.75))
    if stats["checked"] < sample:
        return False
    return stats["lost"] > stats["checked"] * share


def _pause(state: StockCheckSourceState, reason: str, now) -> None:
    state.paused_reason = reason
    state.paused_at = now
    state.save(update_fields=["paused_reason", "paused_at", "stats", "cursor_pk", "updated_at"])
    title = SOURCE_TITLES.get(state.parser_key, state.parser_key)
    _alert(
        f"⚠️ Ночная сверка наличия: {title} на паузе.\n{reason}\n"
        "Товары дальше не трогаются. Продолжить — админка «Ночная сверка наличия», очистить поле «Пауза»."
    )


def run_nightly_batch(
    *,
    now: datetime | None = None,
    budget_seconds: int | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    service: NightlyStockCheckService | None = None,
) -> dict[str, Any]:
    """Одна пачка сверки: по очереди по источникам, не дольше бюджета и конца тихих часов."""
    if not getattr(settings, "NIGHTLY_STOCK_CHECK_ENABLED", False):
        return {"status": "disabled"}
    now = now or timezone.now()
    end = window_end(now)
    if end is None:
        return {"status": "outside_window"}
    sources = nightly_sources()
    if not sources:
        return {"status": "no_sources"}
    budget = budget_seconds or _setting_int(
        "NIGHTLY_STOCK_CHECK_BATCH_SECONDS", 480, minimum=30, maximum=3000
    )
    budget = min(budget, max((end - timezone.localtime(now)).total_seconds(), 0))
    token = uuid.uuid4().hex
    if not cache.add(BATCH_LOCK_KEY, token, timeout=int(budget) + 300):
        return {"status": "already_running"}
    try:
        return _run_batch(sources, now=now, budget=budget, clock=clock, sleep=sleep,
                          service=service or NightlyStockCheckService())
    finally:
        if cache.get(BATCH_LOCK_KEY) == token:
            cache.delete(BATCH_LOCK_KEY)


def _run_batch(sources, *, now, budget, clock, sleep, service) -> dict[str, Any]:
    night = timezone.localdate(now)
    deadline = clock() + budget
    # Одна проверка LCW — карточка и все цвета, до минуты при медленном сайте.
    reserve = _setting_int("NIGHTLY_STOCK_CHECK_RESERVE_SECONDS", 90, minimum=0, maximum=600)
    max_errors = _setting_int("NIGHTLY_STOCK_CHECK_MAX_CONSECUTIVE_ERRORS", 10, minimum=1, maximum=1000)
    states: dict[str, StockCheckSourceState] = {}
    queues: dict[str, list[int]] = {}
    summary: dict[str, Any] = {"status": "completed", "sources": {}}
    for key in sources:
        state, _ = StockCheckSourceState.objects.get_or_create(parser_key=key)
        _reset_night(state, night)
        if state.paused_reason:
            summary["sources"][key] = "paused"
        elif state.stats.get("stopped"):
            summary["sources"][key] = state.stats["stopped"]
        elif source_scrape_running(key):
            summary["sources"][key] = "scraper_running"
        else:
            states[key] = state
            queues[key] = []
    next_at = {key: clock() for key in states}
    consecutive = {key: 0 for key in states}
    while states and clock() + reserve < deadline:
        key = min(states, key=next_at.get)
        state = states[key]
        wait = next_at[key] - clock()
        if wait > 0:
            if clock() + wait + reserve >= deadline:
                break
            sleep(wait)
        if not queues[key]:
            queues[key] = _next_product_ids(key, state.cursor_pk)
            if not queues[key]:
                # Весь каталог источника проверен: следующая ночь начнёт сначала.
                state.cursor_pk = 0
                state.last_full_cycle_at = timezone.now()
                state.stats["stopped"] = "cycle_done"
                state.save(update_fields=["cursor_pk", "last_full_cycle_at", "stats", "updated_at"])
                summary["sources"][key] = "cycle_done"
                del states[key]
                continue
        product_id = queues[key].pop(0)
        started = clock()
        before = Product.objects.filter(pk=product_id).values_list("is_available", "price").first()
        if before is None:
            state.cursor_pk = product_id
            continue
        result = service.run(product_id)
        outcome = _record(state, product_id, before, result)
        state.cursor_pk = product_id
        next_at[key] = max(started + 60.0 / source_rate_per_minute(key), clock())
        consecutive[key] = consecutive[key] + 1 if outcome == "retryable" else 0
        if outcome == "paid_access_unavailable":
            _pause(state, "Источник требует платный прокси — ночная сверка его не открывает.", timezone.now())
            summary["sources"][key] = "paused"
        elif _loss_tripped(state.stats):
            _pause(
                state,
                f"За ночь пропало или закончилось {state.stats['lost']} из {state.stats['checked']} "
                "проверенных товаров «в наличии» — больше похоже на сбой парсера, чем на продавца.",
                timezone.now(),
            )
            summary["sources"][key] = "paused"
        elif consecutive[key] >= max_errors:
            # Сайт не отвечает или ограничил запросы — до следующей ночи его не трогаем.
            state.stats["stopped"] = "source_errors"
            state.save(update_fields=["stats", "cursor_pk", "updated_at"])
            summary["sources"][key] = "source_errors"
        else:
            state.save(update_fields=["stats", "cursor_pk", "updated_at"])
            continue
        del states[key]
    for key, state in states.items():
        summary["sources"].setdefault(key, dict(state.stats))
    logger.info("nightly_stock_check_batch", extra={"summary": summary})
    return summary


def _plural_nights(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return "ночь"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return "ночи"
    return "ночей"


def build_night_report(night=None) -> str:
    """Итог ночи простыми словами для владельца."""
    night = night or timezone.localdate()
    lines = [f"🌙 Ночная сверка наличия {night:%d.%m}"]
    for state in StockCheckSourceState.objects.filter(parser_key__in=nightly_sources()).order_by("parser_key"):
        title = SOURCE_TITLES.get(state.parser_key, state.parser_key)
        if state.paused_reason:
            lines.append(f"{title}: на паузе — {state.paused_reason}")
            continue
        if state.night != night:
            lines.append(f"{title}: этой ночью не запускалась.")
            continue
        stats = state.stats
        checked = stats.get("checked", 0)
        line = f"{title}: проверено {checked} из {state.catalog_size}"
        if checked and state.catalog_size > checked and stats.get("stopped") != "cycle_done":
            nights = -(-state.catalog_size // checked)
            line += f" (весь каталог — примерно за {nights} {_plural_nights(nights)})"
        line += (
            f". Закончились: {stats.get('became_unavailable', 0)}, снова в наличии: "
            f"{stats.get('became_available', 0)}, цена изменилась: {stats.get('price_changed', 0)}."
        )
        if stats.get("gone"):
            line += f" Нет у продавца: {stats['gone']} (новых {stats.get('new_candidates', 0)})."
        if stats.get("errors") or stats.get("rejected"):
            line += f" Не удалось проверить: {stats.get('errors', 0) + stats.get('rejected', 0)}."
        if stats.get("stopped") == "source_errors":
            line += " Сайт перестал отвечать — остановились до следующей ночи."
        lines.append(line)
    waiting = StaleProductCandidate.objects.filter(status=StaleProductCandidate.Status.CANDIDATE).count()
    if waiting:
        lines.append(f"Товаров, которых нет у продавца: {waiting} — админка «Неактуальные товары».")
    return "\n".join(lines)


def send_night_report(night=None) -> dict[str, Any]:
    if not getattr(settings, "NIGHTLY_STOCK_CHECK_ENABLED", False):
        return {"status": "disabled"}
    night = night or timezone.localdate()
    pending = StockCheckSourceState.objects.filter(parser_key__in=nightly_sources()).exclude(reported_night=night)
    if not pending.exists():
        return {"status": "already_reported"}
    text = build_night_report(night)
    _alert(text)
    pending.update(reported_night=night)
    return {"status": "sent", "text": text}
