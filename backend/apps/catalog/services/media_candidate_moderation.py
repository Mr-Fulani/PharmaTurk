"""Explicit moderation workflow for media-enrichment candidates."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

import imagehash
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.catalog.models import (
    MediaEnrichmentCandidate,
    MediaEnrichmentCandidateStatus,
    MediaEnrichmentStatus,
)
from apps.recommendations.services import safe_image_fetcher

ALL_CANDIDATES_REJECTED = "Все найденные изображения отклонены модератором"


class MediaCandidateModerationError(Exception):
    """A candidate cannot be safely promoted to a product gallery."""


@dataclass(frozen=True)
class MediaCandidateModerationResult:
    changed: bool
    gallery_created: bool = False


def _read_and_validate_candidate(candidate: MediaEnrichmentCandidate) -> bytes:
    if not candidate.image_file:
        raise MediaCandidateModerationError("candidate_file_missing")

    try:
        with candidate.image_file.open("rb") as candidate_file:
            content = candidate_file.read(safe_image_fetcher.MAX_IMAGE_BYTES + 1)
    except Exception as exc:
        raise MediaCandidateModerationError("candidate_file_unreadable") from exc

    if len(content) > safe_image_fetcher.MAX_IMAGE_BYTES:
        raise MediaCandidateModerationError("candidate_file_too_large")
    if hashlib.sha256(content).hexdigest() != candidate.content_hash:
        raise MediaCandidateModerationError("candidate_hash_mismatch")

    validated = safe_image_fetcher.validate_image_bytes(content)
    validated.image.close()
    return content


def _find_visual_duplicate(product, image_hash: str | None):
    if not image_hash:
        return None
    current_hash = imagehash.hex_to_hash(image_hash)
    for gallery_image in product.gallery_images.exclude(image_hash__isnull=True).exclude(
        image_hash=""
    ):
        try:
            if current_hash - imagehash.hex_to_hash(gallery_image.image_hash) < 10:
                return gallery_image
        except (TypeError, ValueError):
            continue
    return None


def _sync_product_moderation_status(product) -> None:
    candidates = product.media_enrichment_candidates.all()
    if candidates.filter(status=MediaEnrichmentCandidateStatus.PENDING).exists():
        status = MediaEnrichmentStatus.MODERATION
        error = None
    elif candidates.filter(status=MediaEnrichmentCandidateStatus.APPROVED).exists():
        status = MediaEnrichmentStatus.COMPLETED
        error = None
    elif candidates.filter(status=MediaEnrichmentCandidateStatus.REJECTED).exists():
        status = MediaEnrichmentStatus.COMPLETED
        error = ALL_CANDIDATES_REJECTED
    else:
        return

    product.media_enrichment_status = status
    product.media_enrichment_error = error
    product.media_enrichment_last_at = timezone.now()
    product.save(
        update_fields=[
            "media_enrichment_status",
            "media_enrichment_error",
            "media_enrichment_last_at",
        ]
    )


def approve_media_candidate(
    candidate_id: int,
    *,
    reviewer,
) -> MediaCandidateModerationResult:
    """Promote one reviewed candidate to the product gallery exactly once."""

    with transaction.atomic():
        candidate = (
            MediaEnrichmentCandidate.objects.select_for_update(of=("self",))
            .select_related("medicine_product", "supplement_product")
            .get(pk=candidate_id)
        )
        if candidate.status != MediaEnrichmentCandidateStatus.PENDING:
            return MediaCandidateModerationResult(changed=False)

        product = candidate.product
        if product is None:
            raise MediaCandidateModerationError("candidate_product_missing")

        content = _read_and_validate_candidate(candidate)
        duplicate = _find_visual_duplicate(product, candidate.image_hash)
        gallery_created = False

        if duplicate is None:
            ImageModel = product.gallery_images.model
            next_sort_order = (
                product.gallery_images.aggregate(max_order=Max("sort_order"))["max_order"] or 0
            ) + 1
            image_record = ImageModel(
                product=product,
                image_url=candidate.source_url,
                alt_text=str(product.name or "")[:200],
                sort_order=next_sort_order,
                is_main=not product.gallery_images.filter(is_main=True).exists(),
                image_hash=candidate.image_hash,
            )
            filename = os.path.basename(candidate.image_file.name) or (
                f"candidate-{candidate.pk}.jpg"
            )
            image_record.image_file.save(filename, ContentFile(content), save=False)
            image_record.save()
            gallery_created = True

        candidate.status = MediaEnrichmentCandidateStatus.APPROVED
        candidate.reviewed_by = reviewer
        candidate.reviewed_at = timezone.now()
        if duplicate is not None and not candidate.moderation_note:
            candidate.moderation_note = "Одобрено; изображение уже присутствует в галерее"
        candidate.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "moderation_note",
                "updated_at",
            ]
        )
        _sync_product_moderation_status(product)
        return MediaCandidateModerationResult(
            changed=True,
            gallery_created=gallery_created,
        )


def reject_media_candidate(
    candidate_id: int,
    *,
    reviewer,
) -> MediaCandidateModerationResult:
    """Reject a candidate without touching the product gallery."""

    with transaction.atomic():
        candidate = (
            MediaEnrichmentCandidate.objects.select_for_update(of=("self",))
            .select_related("medicine_product", "supplement_product")
            .get(pk=candidate_id)
        )
        if candidate.status != MediaEnrichmentCandidateStatus.PENDING:
            return MediaCandidateModerationResult(changed=False)

        product = candidate.product
        candidate.status = MediaEnrichmentCandidateStatus.REJECTED
        candidate.reviewed_by = reviewer
        candidate.reviewed_at = timezone.now()
        if not candidate.moderation_note:
            candidate.moderation_note = "Отклонено модератором"
        candidate.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "moderation_note",
                "updated_at",
            ]
        )
        if product is not None:
            _sync_product_moderation_status(product)
        return MediaCandidateModerationResult(changed=True)
