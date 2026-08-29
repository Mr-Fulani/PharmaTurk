import io

import pytest
from django.contrib.auth import get_user_model
from PIL import Image

from apps.catalog.models import (
    MediaEnrichmentCandidateStatus,
    MediaEnrichmentStatus,
    MedicineProduct,
    MedicineProductImage,
    SupplementProduct,
    SupplementProductImage,
)
from apps.catalog.services.media_candidate_moderation import (
    ALL_CANDIDATES_REJECTED,
    approve_media_candidate,
    reject_media_candidate,
)
from apps.catalog.services.medicine_media_enricher import (
    FetchedMedicineImage,
    MedicineImageSearchCandidate,
    MedicineMediaEnricher,
)


def _fetched_image(color=(20, 40, 60)) -> FetchedMedicineImage:
    output = io.BytesIO()
    Image.new("RGB", (500, 500), color=color).save(output, "JPEG")
    return FetchedMedicineImage(
        content=output.getvalue(),
        extension=".jpg",
        width=500,
        height=500,
    )


@pytest.fixture
def moderator(db):
    return get_user_model().objects.create_user(
        email="media-moderator@example.test",
        username="media-moderator",
        password="not-used",
        is_staff=True,
    )


@pytest.fixture
def medicine(db):
    return MedicineProduct.objects.create(
        name="Moderated medicine",
        slug="moderated-medicine",
        barcode="8699999999991",
        price=100,
        currency="TRY",
    )


def _stage_candidate(
    product,
    *,
    requested_by,
    url="https://images.example.test/moderated-medicine.jpg?token=secret",
):
    enricher = MedicineMediaEnricher()
    candidate = enricher.stage_validated_candidate(
        product,
        MedicineImageSearchCandidate(
            url=url,
            source="serper",
            query=product.name,
        ),
        _fetched_image(),
        requested_by=requested_by,
    )
    assert candidate is not None
    return candidate


@pytest.mark.django_db
def test_approval_is_the_only_operation_that_adds_candidate_to_gallery(
    medicine,
    moderator,
):
    candidate = _stage_candidate(medicine, requested_by=moderator)
    assert MedicineProductImage.objects.filter(product=medicine).count() == 0

    result = approve_media_candidate(candidate.pk, reviewer=moderator)

    assert result.changed is True
    assert result.gallery_created is True
    image = MedicineProductImage.objects.get(product=medicine)
    assert image.is_main is True
    assert image.image_url == "https://images.example.test/moderated-medicine.jpg"
    candidate.refresh_from_db()
    assert candidate.status == MediaEnrichmentCandidateStatus.APPROVED
    assert candidate.reviewed_by == moderator
    medicine.refresh_from_db()
    assert medicine.media_enrichment_status == MediaEnrichmentStatus.COMPLETED

    repeated = approve_media_candidate(candidate.pk, reviewer=moderator)
    assert repeated.changed is False
    assert MedicineProductImage.objects.filter(product=medicine).count() == 1

    image.image_file.delete(save=False)
    candidate.image_file.delete(save=False)


@pytest.mark.django_db
def test_rejection_never_changes_product_gallery(medicine, moderator):
    candidate = _stage_candidate(medicine, requested_by=moderator)

    result = reject_media_candidate(candidate.pk, reviewer=moderator)

    assert result.changed is True
    assert MedicineProductImage.objects.filter(product=medicine).count() == 0
    candidate.refresh_from_db()
    assert candidate.status == MediaEnrichmentCandidateStatus.REJECTED
    assert candidate.reviewed_by == moderator
    medicine.refresh_from_db()
    assert medicine.media_enrichment_status == MediaEnrichmentStatus.COMPLETED
    assert medicine.media_enrichment_error == ALL_CANDIDATES_REJECTED

    candidate.image_file.delete(save=False)


@pytest.mark.django_db
def test_supplement_candidate_also_requires_explicit_approval(moderator):
    supplement = SupplementProduct.objects.create(
        name="Moderated supplement",
        slug="moderated-supplement",
        gtin="8699999999992",
        price=75,
        currency="TRY",
    )
    candidate = _stage_candidate(
        supplement,
        requested_by=moderator,
        url="https://images.example.test/moderated-supplement.jpg",
    )
    assert SupplementProductImage.objects.filter(product=supplement).count() == 0

    approve_media_candidate(candidate.pk, reviewer=moderator)

    image = SupplementProductImage.objects.get(product=supplement)
    candidate.refresh_from_db()
    assert candidate.status == MediaEnrichmentCandidateStatus.APPROVED
    assert candidate.supplement_product == supplement
    image.image_file.delete(save=False)
    candidate.image_file.delete(save=False)
