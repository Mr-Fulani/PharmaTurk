from celery import shared_task
import logging
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.models import AIProcessingLog

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def process_product_ai_task(self, product_id: int, processing_type: str = 'full', auto_apply: bool = False):
    """
    Celery task for AI product processing.
    """
    try:
        logger.info(f"Starting AI processing for product {product_id}, type={processing_type}")
        
        generator = ContentGenerator()
        log_entry = generator.process_product(
            product_id=product_id,
            processing_type=processing_type,
            auto_apply=auto_apply
        )
        
        logger.info(f"AI processing completed for product {product_id}. Log ID: {log_entry.id}")
        return {
            'status': 'success',
            'log_id': log_entry.id,
            'product_id': product_id
        }
        
    except Exception as e:
        logger.error(f"Error in AI task for product {product_id}: {e}")
        # Retry only for specific errors if needed
        # self.retry(exc=e, countdown=60)
        return {
            'status': 'error',
            'error': str(e),
            'product_id': product_id
        }
