import io
import hashlib
import logging
import os
import re
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlsplit, urlunsplit

import httpx
import imagehash
from PIL import Image
from django.conf import settings
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db import models
from django.utils import timezone
from django.utils.text import get_valid_filename

from apps.catalog.models import (
    MediaEnrichmentCandidate,
    MediaEnrichmentCandidateStatus,
    MediaEnrichmentStatus,
)
from apps.recommendations.services import safe_image_fetcher

logger = logging.getLogger(__name__)

MEDIA_ENRICHMENT_MAX_IMAGES = "Достигнуто максимальное количество изображений или кандидатов"
MEDIA_ENRICHMENT_RECENT_NO_RESULT = "Недавний поиск уже завершился без результата"
MEDIA_ENRICHMENT_NO_CANDIDATES = "Изображений не найдено"
MEDIA_ENRICHMENT_NO_VALID_CANDIDATES = "Подходящие изображения не прошли проверку"
MEDIA_ENRICHMENT_AWAITING_MODERATION = "Найденные изображения ожидают модерации"
MEDIA_ENRICHMENT_PROVIDER_UNAVAILABLE = "Сервис поиска изображений недоступен"


def _candidate_host(url: str) -> str:
    """Return a query-free diagnostic label for an untrusted candidate URL."""
    try:
        return (urlsplit(url).hostname or "invalid-host")[:253]
    except (TypeError, ValueError):
        return "invalid-host"


def _query_free_source_url(url: str) -> str:
    """Avoid persisting short-lived CDN signatures after the bytes are saved."""
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


@dataclass(frozen=True)
class FetchedMedicineImage:
    """A fully fetched and decoded image that is safe to persist."""

    content: bytes
    extension: str
    width: int
    height: int


@dataclass(frozen=True)
class MedicineImageSearchCandidate:
    """Search metadata retained until a moderator reviews the downloaded file."""

    url: str
    source: str
    query: str = ""


class MediaSearchProviderError(RuntimeError):
    """An upstream search provider failed instead of returning an empty result."""

    def __init__(self, provider: str, code: str, detail: str = ""):
        self.provider = provider
        self.code = code
        self.detail = " ".join(str(detail or "").split())[:160]
        super().__init__(self.user_message)

    @property
    def user_message(self) -> str:
        message = f"{self.provider}: {self.code}"
        return f"{message} ({self.detail})" if self.detail else message


def _provider_error_detail(response: httpx.Response) -> str:
    """Extract a short provider error without logging headers or credentials."""
    try:
        payload = response.json()
    except ValueError:
        return ""
    if not isinstance(payload, dict):
        return ""
    for key in ("message", "error", "detail"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _valid_gtin(value: object) -> str:
    candidate = str(value or "").strip()
    return candidate if candidate.isdigit() and len(candidate) in {8, 12, 13, 14} else ""


def _compact_search_name(value: object) -> str:
    """Prefer the Latin commercial name over localized descriptive suffixes."""
    name = " ".join(str(value or "").split())
    without_parenthetical = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    latin_prefix = re.match(r"^[A-Za-z0-9][A-Za-z0-9\s+%./-]*", without_parenthetical)
    if latin_prefix:
        compact = " ".join(latin_prefix.group(0).split())
        if len(compact) >= 3:
            return compact
    return without_parenthetical


class OpenFoodFactsClient:
    """Client for fetching images from Open Food Facts API using barcode."""
    
    BASE_URL = "https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    
    def fetch_images(self, barcode: str) -> List[str]:
        if not barcode:
            return []
            
        url = self.BASE_URL.format(barcode=barcode)
        try:
            import time
            with httpx.Client(timeout=15.0) as client:
                response = client.get(url)
                
                # Обработка лимитов (Error 429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning("Open Food Facts rate limit reached. Waiting %d seconds...", retry_after)
                    time.sleep(retry_after)
                    response = client.get(url) # Retry once
                
                response.raise_for_status()
                data = response.json()
                
                if data.get("status") != 1:
                    logger.info("Product with barcode %s not found in Open Food Facts", barcode)
                    return []
                    
                product_data = data.get("product", {})
                images = product_data.get("images", {})
                
                urls = []
                for key, img_data in images.items():
                    # We are interested in original uploaded images or full-sized ones
                    # Typically keys are numbers or 'front', 'ingredients', etc.
                    # Open Food Facts stores full URLs under 'image_url' or similar, but the structure can be tricky.
                    # Let's extract 'image_url', 'image_front_url' directly from product_data first.
                    pass
                
                # Simpler extraction of main images
                for field in ["image_url", "image_front_url", "image_ingredients_url", "image_nutrition_url"]:
                    img_url = product_data.get(field)
                    if img_url and isinstance(img_url, str):
                        urls.append(img_url)
                        
                return list(set(urls))
                
        except Exception as e:
            logger.error("Error fetching from Open Food Facts for barcode %s: %s", barcode, e)
            return []


class SerperImageSearchClient:
    """Client for fetching images from Serper.dev API (Google Search unofficial)."""
    
    BASE_URL = "https://google.serper.dev/images"
    
    def __init__(self):
        self.api_key = settings.SERPER_API_KEY
        
    def fetch_images(self, query: str) -> List[str]:
        if not self.api_key or not query:
            return []
            
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "q": query,
            "num": 10  # Get top 10 images
        }
        
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(self.BASE_URL, headers=headers, json=payload)
        except httpx.RequestError as error:
            raise MediaSearchProviderError(
                "Serper",
                "ошибка сети",
                type(error).__name__,
            ) from error

        if response.is_error:
            raise MediaSearchProviderError(
                "Serper",
                f"HTTP {response.status_code}",
                _provider_error_detail(response),
            )
        try:
            data = response.json()
        except ValueError as error:
            raise MediaSearchProviderError("Serper", "некорректный ответ") from error

        if not isinstance(data, dict):
            raise MediaSearchProviderError("Serper", "некорректный ответ")
        return [
            item.get("imageUrl")
            for item in data.get("images", [])
            if isinstance(item, dict) and item.get("imageUrl")
        ]


class MedicineMediaEnricher:
    """Service to enrich MedicineProduct with images from external sources."""
    
    def __init__(self):
        self.open_food_facts_client = OpenFoodFactsClient()
        self.serper_client = SerperImageSearchClient()
        self.min_width = settings.MEDICINE_MEDIA_MIN_WIDTH
        self.min_height = settings.MEDICINE_MEDIA_MIN_HEIGHT
        self.search_errors: list[MediaSearchProviderError] = []
        
    def build_search_queries(self, product: models.Model) -> List[str]:
        queries = []
        name = product.name or ""
        search_name = _compact_search_name(name)
        active_ingredient = getattr(product, 'active_ingredient', "")
        
        if search_name and active_ingredient:
            queries.append(f"{search_name} {active_ingredient}")
            
        if search_name:
            queries.append(search_name)

        if name and name != search_name:
            queries.append(name)
            
        # Add ATC code context if available
        atc_code = getattr(product, 'atc_code', "")
        if atc_code and search_name:
            queries.append(f"{search_name} {atc_code}")
            
        return list(dict.fromkeys(queries))  # Remove duplicates preserving order

    def fetch_candidates(self, product: models.Model) -> List[MedicineImageSearchCandidate]:
        candidates = []
        self.search_errors = []
        
        # 1. Open Food Facts
        barcode = _valid_gtin(
            getattr(product, 'barcode', getattr(product, 'gtin', ''))
        )
        if barcode:
            logger.info("Product %s has barcode %s. Searching in Open Food Facts...", product.id, barcode)
            off_urls = self.open_food_facts_client.fetch_images(barcode)
            candidates.extend(
                MedicineImageSearchCandidate(
                    url=url,
                    source="open_food_facts",
                    query=str(barcode),
                )
                for url in off_urls
            )
            logger.info("Open Food Facts returned %d candidates for product %s.", len(off_urls), product.id)
        else:
            logger.info("Product %s has no barcode. Skipping Open Food Facts.", product.id)
            
        # 2. Serper Image Search
        serper_key = getattr(settings, 'SERPER_API_KEY', None)
        if serper_key:
            queries = self.build_search_queries(product)
            logger.info("Searching in Serper Image Search with queries: %s", queries)
            for query in queries:
                try:
                    serper_urls = self.serper_client.fetch_images(query)
                    logger.info("Serper Image Search returned %d candidates for query '%s'.", len(serper_urls), query)
                    candidates.extend(
                        MedicineImageSearchCandidate(
                            url=url,
                            source="serper",
                            query=query,
                        )
                        for url in serper_urls
                    )
                except MediaSearchProviderError as error:
                    self.search_errors.append(error)
                    logger.error(
                        "Serper image search failed for product %s: %s",
                        product.id,
                        error.user_message,
                    )
                    break
                except Exception as error:
                    provider_error = MediaSearchProviderError(
                        "Serper",
                        "внутренняя ошибка клиента",
                        type(error).__name__,
                    )
                    self.search_errors.append(provider_error)
                    logger.exception(
                        "Unexpected Serper client failure for product %s",
                        product.id,
                    )
                    break
                
                if len(candidates) >= 10:  # Cap candidates to avoid excessive requests
                    logger.info("Reached maximum candidate limit (10). Stopping Serper search.")
                    break
        else:
            logger.warning("SERPER_API_KEY is not set or empty in settings. Serper search disabled.")
            self.search_errors.append(
                MediaSearchProviderError("Serper", "API-ключ не настроен")
            )
                    
        unique_candidates = {}
        for candidate in candidates:
            unique_candidates.setdefault(candidate.url, candidate)
        return list(unique_candidates.values())

    def fetch_validated_image(self, url: str) -> Optional[FetchedMedicineImage]:
        """Fetch one candidate once, with SSRF, byte and decode limits enforced."""
        candidate_host = _candidate_host(url)
        logger.info("Fetching image candidate from host=%s", candidate_host)
        try:
            image_data, content_type = safe_image_fetcher.fetch_public_image_bytes(url)
            validated = safe_image_fetcher.validate_image_bytes(
                image_data,
                expected_content_type=content_type,
            )
            try:
                width, height = validated.image.size
                image_format = validated.format
            finally:
                validated.image.close()

            if width < self.min_width or height < self.min_height:
                logger.warning(
                    "Image from host=%s is too small (%dx%d). Required minimum is %dx%d.",
                    candidate_host,
                    width,
                    height,
                    self.min_width,
                    self.min_height,
                )
                return None

            extension = safe_image_fetcher.FORMAT_EXTENSIONS[image_format]
            logger.info("Image from host=%s is valid. Size: %dx%d.", candidate_host, width, height)
            return FetchedMedicineImage(
                content=image_data,
                extension=extension,
                width=width,
                height=height,
            )
        except safe_image_fetcher.ImageFetchError as error:
            logger.warning("Image candidate rejected for host=%s: %s", candidate_host, error.code)
            return None
        except Exception:
            logger.error("Unexpected image validation failure for host=%s", candidate_host)
            return None

    def get_image_hash(self, image_data: bytes) -> Optional[str]:
        try:
            from PIL import ImageChops
            img = Image.open(io.BytesIO(image_data)).convert('RGB')
            # Trim white borders to improve hash matching for identical images with different padding
            bg = Image.new(img.mode, img.size, (255, 255, 255))
            diff = ImageChops.difference(img, bg)
            diff = ImageChops.add(diff, diff, 2.0, -100)
            bbox = diff.getbbox()
            if bbox:
                img = img.crop(bbox)
            return str(imagehash.phash(img))
        except Exception as e:
            logger.warning("Failed to calculate image hash: %s", e)
            return None

    def _is_visual_duplicate(self, product: models.Model, current_hash: str) -> bool:
        current = imagehash.hex_to_hash(current_hash)
        for existing_image in product.gallery_images.all():
            existing_hash = existing_image.image_hash
            if not existing_hash and existing_image.image_file:
                try:
                    with existing_image.image_file.open("rb") as image_file:
                        existing_hash = self.get_image_hash(image_file.read())
                    if existing_hash:
                        existing_image.image_hash = existing_hash
                        existing_image.save(update_fields=["image_hash"])
                except Exception as error:
                    logger.warning(
                        "Could not compute hash for existing image %s: %s",
                        existing_image.id,
                        error,
                    )
            try:
                if existing_hash and current - imagehash.hex_to_hash(existing_hash) < 10:
                    return True
            except (TypeError, ValueError):
                continue

        for existing_candidate in product.media_enrichment_candidates.exclude(
            image_hash__isnull=True
        ).exclude(image_hash=""):
            try:
                if current - imagehash.hex_to_hash(existing_candidate.image_hash) < 10:
                    return True
            except (TypeError, ValueError):
                continue
        return False

    def stage_validated_candidate(
        self,
        product: models.Model,
        candidate: MedicineImageSearchCandidate,
        fetched: FetchedMedicineImage,
        *,
        requested_by,
    ) -> Optional[MediaEnrichmentCandidate]:
        """Persist a quarantined candidate without modifying the product gallery."""

        candidate_record = None
        created = False
        try:
            if not (
                requested_by
                and getattr(requested_by, "pk", None)
                and getattr(requested_by, "is_active", False)
                and getattr(requested_by, "is_staff", False)
            ):
                raise ValueError("Active staff initiator is required")

            current_hash = self.get_image_hash(fetched.content)
            if current_hash and self._is_visual_duplicate(product, current_hash):
                logger.info(
                    "Candidate from host=%s duplicates an existing image/candidate for product %s.",
                    _candidate_host(candidate.url),
                    product.id,
                )
                return None

            content_hash = hashlib.sha256(fetched.content).hexdigest()
            candidate_key = hashlib.sha256(
                f"{product._meta.label_lower}:{product.pk}:{content_hash}".encode("utf-8")
            ).hexdigest()
            product_field = {
                "medicineproduct": "medicine_product",
                "supplementproduct": "supplement_product",
            }.get(product._meta.model_name)
            if product_field is None:
                raise ValueError("Unsupported media-enrichment product model")

            candidate_record, created = MediaEnrichmentCandidate.objects.get_or_create(
                candidate_key=candidate_key,
                defaults={
                    product_field: product,
                    "source": candidate.source[:64],
                    "source_host": _candidate_host(candidate.url),
                    "source_url": _query_free_source_url(candidate.url),
                    "search_query": candidate.query[:1000],
                    "content_hash": content_hash,
                    "image_hash": current_hash,
                    "width": fetched.width,
                    "height": fetched.height,
                    "status": MediaEnrichmentCandidateStatus.PENDING,
                    "requested_by": requested_by,
                },
            )
            if not created:
                return None

            parsed_path = urlsplit(candidate.url).path
            original_stem = os.path.splitext(os.path.basename(parsed_path))[0]
            safe_stem = get_valid_filename(original_stem)[:100].strip("._-")
            if not safe_stem:
                safe_stem = f"product_{product.id}_candidate"
            candidate_record.image_file.save(
                f"{safe_stem}{fetched.extension}",
                ContentFile(fetched.content),
                save=True,
            )
            logger.info(
                "Staged image candidate %s from host=%s for product %s.",
                candidate_record.pk,
                _candidate_host(candidate.url),
                product.id,
            )
            return candidate_record
        except Exception as error:
            if created and candidate_record is not None:
                try:
                    if candidate_record.image_file:
                        candidate_record.image_file.delete(save=False)
                    candidate_record.delete()
                except Exception:
                    logger.warning(
                        "Could not roll back failed candidate %s.",
                        candidate_record.pk,
                    )
            logger.error(
                "Failed to stage candidate from host=%s for product %s (error=%s)",
                _candidate_host(candidate.url),
                product.id,
                type(error).__name__,
            )
            return None

    def process_candidate(
        self,
        product: models.Model,
        candidate: MedicineImageSearchCandidate,
        *,
        requested_by,
    ) -> Optional[MediaEnrichmentCandidate]:
        """Fetch and quarantine a candidate without touching the product gallery."""
        fetched = self.fetch_validated_image(candidate.url)
        if fetched is None:
            return None
        return self.stage_validated_candidate(
            product,
            candidate,
            fetched,
            requested_by=requested_by,
        )

    def enrich(
        self,
        product: models.Model,
        max_images: int,
        ignore_cache: bool = False,
        *,
        requested_by,
    ) -> int:
        logger.info("Starting manual enrichment for product ID: %s", product.id)
        pending_count = product.media_enrichment_candidates.filter(
            status=MediaEnrichmentCandidateStatus.PENDING
        ).count()
        current_count = product.gallery_images.count() + pending_count
        if current_count >= max_images:
            product.media_enrichment_status = (
                MediaEnrichmentStatus.MODERATION
                if pending_count
                else MediaEnrichmentStatus.COMPLETED
            )
            product.media_enrichment_last_at = timezone.now()
            product.media_enrichment_error = (
                MEDIA_ENRICHMENT_AWAITING_MODERATION
                if pending_count
                else MEDIA_ENRICHMENT_MAX_IMAGES
            )
            product.save(update_fields=[
                'media_enrichment_status',
                'media_enrichment_last_at',
                'media_enrichment_error',
            ])
            return 0
            
        # Check cache to avoid hitting APIs if we already tried and failed recently
        cache_key = f"media_enrich_failed:{product._meta.label_lower}:{product.id}"
        if not ignore_cache and cache.get(cache_key):
            logger.info("Product %s is in failed cache (no images found recently). Skipping to save API limits.", product.id)
            product.media_enrichment_status = MediaEnrichmentStatus.COMPLETED
            product.media_enrichment_last_at = timezone.now()
            product.media_enrichment_error = MEDIA_ENRICHMENT_RECENT_NO_RESULT
            product.save(update_fields=[
                'media_enrichment_status',
                'media_enrichment_last_at',
                'media_enrichment_error',
            ])
            return 0
            
        product.media_enrichment_status = MediaEnrichmentStatus.PROCESSING
        product.media_enrichment_error = None
        product.save(update_fields=['media_enrichment_status', 'media_enrichment_error'])
            
        try:
            candidates = self.fetch_candidates(product)
            if not candidates:
                if self.search_errors:
                    error_message = "; ".join(
                        error.user_message for error in self.search_errors
                    )[:1000]
                    logger.warning(
                        "Image search provider failed for product %s: %s",
                        product.id,
                        error_message,
                    )
                    cache.delete(cache_key)
                    product.media_enrichment_status = MediaEnrichmentStatus.FAILED
                    product.media_enrichment_last_at = timezone.now()
                    product.media_enrichment_error = (
                        f"{MEDIA_ENRICHMENT_PROVIDER_UNAVAILABLE}: {error_message}"
                    )
                    product.save(
                        update_fields=[
                            'media_enrichment_status',
                            'media_enrichment_last_at',
                            'media_enrichment_error',
                        ]
                    )
                    return 0

                logger.info("No candidates found for product %s. Caching failure for 7 days.", product.id)
                cache.set(cache_key, True, timeout=604800)
                
                product.media_enrichment_status = MediaEnrichmentStatus.COMPLETED
                product.media_enrichment_last_at = timezone.now()
                product.media_enrichment_error = MEDIA_ENRICHMENT_NO_CANDIDATES
                product.save(update_fields=['media_enrichment_status', 'media_enrichment_last_at', 'media_enrichment_error'])
                return 0
                
            staged_count = 0
            for candidate in candidates:
                if current_count + staged_count >= max_images:
                    break
                source_url = _query_free_source_url(candidate.url)
                if product.gallery_images.filter(image_url=source_url).exists():
                    continue
                if product.media_enrichment_candidates.filter(source_url=source_url).exists():
                    continue
                if self.process_candidate(
                    product,
                    candidate,
                    requested_by=requested_by,
                ):
                    staged_count += 1

            pending_exists = product.media_enrichment_candidates.filter(
                status=MediaEnrichmentCandidateStatus.PENDING
            ).exists()
            if staged_count == 0 and not pending_exists:
                if self.search_errors:
                    cache.delete(cache_key)
                    product.media_enrichment_status = MediaEnrichmentStatus.FAILED
                    product.media_enrichment_error = (
                        f"{MEDIA_ENRICHMENT_PROVIDER_UNAVAILABLE}: "
                        + "; ".join(
                            error.user_message for error in self.search_errors
                        )[:1000]
                    )
                else:
                    cache.set(cache_key, True, timeout=604800)
                    product.media_enrichment_status = MediaEnrichmentStatus.COMPLETED
                    product.media_enrichment_error = MEDIA_ENRICHMENT_NO_VALID_CANDIDATES
            else:
                cache.delete(cache_key)
                product.media_enrichment_status = MediaEnrichmentStatus.MODERATION
                product.media_enrichment_error = None

            product.media_enrichment_last_at = timezone.now()
            product.save(update_fields=['media_enrichment_status', 'media_enrichment_last_at', 'media_enrichment_error'])

            logger.info(
                "Finished manual enrichment for product %s. Staged %d candidates.",
                product.id,
                staged_count,
            )
            return staged_count
            
        except Exception as e:
            logger.error(
                "Catastrophic failure during enrichment for product %s (error=%s)",
                product.id,
                type(e).__name__,
            )
            product.media_enrichment_status = MediaEnrichmentStatus.FAILED
            product.media_enrichment_error = type(e).__name__
            product.media_enrichment_last_at = timezone.now()
            product.save(update_fields=['media_enrichment_status', 'media_enrichment_last_at', 'media_enrichment_error'])
            return 0
