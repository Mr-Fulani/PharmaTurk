import logging

import requests
from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(ignore_result=True, autoretry_for=(requests.RequestException,), retry_backoff=True, max_retries=3)
def notify_admin_product_review(review_id: int, event: str = "created"):
    from .models import ProductReview

    review = ProductReview.objects.select_related("user").filter(pk=review_id).first()
    if not review:
        return
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
    chat_id = getattr(settings, "TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.warning("Product review Telegram notification skipped: credentials are missing")
        return

    action = "Новый отзыв" if event == "created" else "Отзыв изменён"
    admin_url = f"{getattr(settings, 'SITE_URL', '').rstrip('/')}/admin/feedback/productreview/{review.pk}/change/"
    text = (
        f"⭐ {action} на модерации\n"
        f"{review.product_name}\n"
        f"Автор: {review.author_name} (@{review.user.username})\n"
        f"Оценка: {review.rating}/5\n"
        f"{review.text[:500]}\n\n"
        f"{admin_url}"
    )
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=10,
    ).raise_for_status()
