from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.catalog.models import Product, Service
from apps.feedback.models import (
    ProductReview,
    ProductReviewMedia,
    Testimonial as PlatformTestimonial,
    TestimonialMedia as PlatformTestimonialMedia,
)
from apps.users.models import User


@pytest.fixture
def feed_user(db):
    return User.objects.create_user(
        email="feed-reviewer@example.com",
        username="feed-reviewer",
        password="password",
        first_name="Feed",
        last_name="Reviewer",
    )


@pytest.fixture
def mixed_reviews(feed_user):
    now = timezone.now()
    platform = PlatformTestimonial.objects.create(
        user=feed_user,
        author_name="Platform author",
        text="Platform review",
        rating=5,
        is_active=True,
    )
    PlatformTestimonial.objects.filter(pk=platform.pk).update(created_at=now - timedelta(days=2))
    platform.refresh_from_db()
    PlatformTestimonialMedia.objects.create(
        testimonial=platform,
        media_type="image",
        image="testimonials/images/platform.jpg",
    )
    PlatformTestimonial.objects.create(
        user=feed_user,
        author_name="Hidden platform author",
        text="Inactive platform review",
        rating=1,
        is_active=False,
    )

    service = ProductReview.objects.create(
        user=feed_user,
        product_type="uslugi",
        product_slug="cleaning-service",
        product_name="Cleaning service",
        author_name="Service author",
        rating=5,
        text="Service review",
        status=ProductReview.Status.APPROVED,
        published_at=now - timedelta(days=3),
        show_on_homepage=True,
        homepage_priority=10,
    )
    ProductReviewMedia.objects.create(
        review=service,
        media_type=ProductReviewMedia.MediaType.VIDEO,
        file="reviews/uslugi/cleaning-service/video.mp4",
    )
    product = ProductReview.objects.create(
        user=feed_user,
        product_type="furniture",
        product_slug="reviewed-chair",
        product_name="Reviewed chair",
        author_name="Product author",
        rating=4,
        text="Product review",
        status=ProductReview.Status.APPROVED,
        published_at=now - timedelta(days=1),
        show_on_homepage=True,
        homepage_priority=20,
    )
    Product.objects.create(
        name="Reviewed chair",
        slug="reviewed-chair",
        product_type="furniture",
        main_image="https://cdn.example.com/reviewed-chair.jpg",
        is_active=True,
    )
    unfeatured = ProductReview.objects.create(
        user=feed_user,
        product_type="books",
        product_slug="reviewed-book",
        product_name="Reviewed book",
        author_name="Book author",
        rating=3,
        text="Approved but not featured",
        status=ProductReview.Status.APPROVED,
        published_at=now,
        show_on_homepage=False,
    )
    ProductReview.objects.create(
        user=feed_user,
        product_type="clothing",
        product_slug="pending-shirt",
        product_name="Pending shirt",
        author_name="Pending author",
        rating=2,
        text="Pending review",
        status=ProductReview.Status.PENDING,
        show_on_homepage=True,
        homepage_priority=1,
    )
    return {
        "platform": platform,
        "service": service,
        "product": product,
        "unfeatured": unfeatured,
    }


@pytest.mark.django_db
def test_homepage_feed_mixes_active_platform_and_selected_approved_reviews(mixed_reviews):
    response = APIClient().get(
        "/api/feedback/reviews-feed/",
        {"placement": "homepage", "page_size": 20},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 3
    assert [item["uid"] for item in response.data["results"]] == [
        f"product_review:{mixed_reviews['service'].pk}",
        f"product_review:{mixed_reviews['product'].pk}",
        f"testimonial:{mixed_reviews['platform'].pk}",
    ]

    service = response.data["results"][0]
    assert service["review_type"] == "service"
    assert service["product_type"] == "uslugi"
    assert service["product_slug"] == "cleaning-service"
    assert service["media"][0]["media_type"] == "video_file"
    assert service["media"][0]["video_file_url"].endswith("video.mp4")
    assert service["subject_image_url"] is None

    product = response.data["results"][1]
    assert product["media"] == []
    assert product["subject_image_url"] == "https://cdn.example.com/reviewed-chair.jpg"

    platform = response.data["results"][2]
    assert platform["review_type"] == "platform"
    assert platform["product_type"] is None
    assert platform["subject_image_url"] is None
    assert platform["media"][0]["image_url"].endswith("platform.jpg")


@pytest.mark.django_db
def test_all_feed_contains_unfeatured_approved_reviews_but_not_pending_or_inactive(mixed_reviews):
    response = APIClient().get(
        "/api/feedback/reviews-feed/",
        {"placement": "all", "page_size": 20},
    )

    assert response.status_code == status.HTTP_200_OK
    returned = {item["uid"] for item in response.data["results"]}
    assert returned == {
        f"testimonial:{mixed_reviews['platform'].pk}",
        f"product_review:{mixed_reviews['service'].pk}",
        f"product_review:{mixed_reviews['product'].pk}",
        f"product_review:{mixed_reviews['unfeatured'].pk}",
    }


@pytest.mark.django_db
def test_service_review_without_own_media_uses_service_image(feed_user):
    service = Service.objects.create(
        name="Delivery service",
        slug="delivery-service",
        main_image="https://cdn.example.com/delivery-service.jpg",
        is_active=True,
    )
    review = ProductReview.objects.create(
        user=feed_user,
        product_type="uslugi",
        product_slug=service.slug,
        product_name=service.name,
        author_name="Service author",
        rating=5,
        text="Service without review media",
        status=ProductReview.Status.APPROVED,
    )

    response = APIClient().get(
        "/api/feedback/reviews-feed/",
        {"placement": "all", "username": feed_user.username, "page_size": 20},
    )

    assert response.status_code == status.HTTP_200_OK
    item = next(row for row in response.data["results"] if row["id"] == review.pk)
    assert item["review_type"] == "service"
    assert item["media"] == []
    assert item["subject_image_url"] == "https://cdn.example.com/delivery-service.jpg"


@pytest.mark.django_db
def test_review_feed_is_paginated_public_and_has_bounded_queries(mixed_reviews, django_assert_max_num_queries):
    with django_assert_max_num_queries(6):
        response = APIClient().get(
            "/api/feedback/reviews-feed/",
            {"placement": "all", "page_size": 2},
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 4
    assert len(response.data["results"]) == 2
    assert response.data["next"] is not None


@pytest.mark.django_db
def test_review_feed_can_be_filtered_by_username(mixed_reviews):
    other = User.objects.create_user(
        email="other-feed-reviewer@example.com",
        username="other-feed-reviewer",
        password="password",
    )
    PlatformTestimonial.objects.create(
        user=other,
        author_name="Other author",
        text="Other review",
        rating=5,
        is_active=True,
    )

    response = APIClient().get(
        "/api/feedback/reviews-feed/",
        {"placement": "all", "username": "other-feed-reviewer", "page_size": 20},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 1
    assert response.data["results"][0]["user_username"] == "other-feed-reviewer"


def test_review_feed_rejects_unknown_placement():
    response = APIClient().get("/api/feedback/reviews-feed/", {"placement": "footer"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
