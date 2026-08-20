import base64
import logging
from io import BytesIO
from typing import Dict, List

from django.conf import settings
from PIL import Image

from apps.catalog.utils.r2_utils import get_r2_client, get_r2_path
from apps.recommendations.services import safe_image_fetcher

logger = logging.getLogger(__name__)


class R2MediaProcessor:
    """
    Обработка медиафайлов из R2 для AI сервисов.
    Оптимизация изображений перед отправкой в Vision API.
    """

    def __init__(self):
        self.s3 = get_r2_client()
        self.bucket = settings.R2_CONFIG["bucket_name"]
        self.cdn_url = (settings.AI_R2_SETTINGS.get("cdn_url") or "").rstrip("/")

    def _get_r2_key(self, image_url: str) -> str | None:
        """Return a key only for URLs below the configured CDN root.

        An empty CDN URL must never turn every external URL into an R2 key.  The
        trailing slash also prevents a hostname such as ``cdn.example.evil``
        from being treated as our own storage.
        """

        if not self.cdn_url or not isinstance(image_url, str):
            return None
        prefix = f"{self.cdn_url}/"
        if not image_url.startswith(prefix):
            return None
        key = image_url[len(prefix) :]
        return key or None

    def _read_r2_image(self, key: str) -> tuple[bytes, str | None]:
        response = self.s3.get_object(Bucket=self.bucket, Key=key)
        content_length = response.get("ContentLength")
        if content_length is not None:
            try:
                declared_size = int(content_length)
                if declared_size < 0:
                    raise safe_image_fetcher.InvalidImageError()
                if declared_size > safe_image_fetcher.MAX_IMAGE_BYTES:
                    raise safe_image_fetcher.ImageTooLargeError()
            except (TypeError, ValueError):
                raise safe_image_fetcher.InvalidImageError() from None

        body = response.get("Body")
        if body is None:
            raise safe_image_fetcher.InvalidImageError()
        image_data = body.read(safe_image_fetcher.MAX_IMAGE_BYTES + 1)
        if len(image_data) > safe_image_fetcher.MAX_IMAGE_BYTES:
            raise safe_image_fetcher.ImageTooLargeError()

        content_type = (
            str(response.get("ContentType") or "").split(";", 1)[0].strip().lower()
        )
        # Older R2 objects may have generic metadata. The decoded format is
        # still strictly validated below; enforce MIME consistency when useful.
        if content_type not in safe_image_fetcher.ALLOWED_CONTENT_TYPES:
            content_type = None
        return image_data, content_type

    def get_image_for_analysis(
        self,
        image_url: str,
        max_size: tuple = (1024, 1024),
        quality: int = 85,
    ) -> Dict:
        """
        Получить оптимизированное изображение для AI анализа.
        
        Args:
            image_url: URL изображения (R2 или внешний)
            max_size: максимальные размеры (width, height)
            quality: качество JPEG (1-100)
        
        Returns:
            {
                'url': str,           # URL для API (временный или оригинал)
                'base64': str,        # Base64 encoded (для OpenAI Vision)
                'format': str,        # 'jpeg', 'png', 'webp'
                'size_bytes': int,
                'dimensions': (w, h)
            }
        """
        
        try:
            key = self._get_r2_key(image_url)
            if key is not None:
                image_data, content_type = self._read_r2_image(key)
            else:
                image_data, content_type = (
                    safe_image_fetcher.fetch_public_image_bytes(image_url)
                )

            validated = safe_image_fetcher.validate_image_bytes(
                image_data,
                expected_content_type=content_type,
            )
            img = validated.image
            original_format = validated.format

            # Resize с сохранением пропорций
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

            # Сохранение в буфер
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
            buffer.seek(0)

            optimized_data = buffer.getvalue()

            # Base64 для OpenAI Vision API
            base64_encoded = base64.b64encode(optimized_data).decode("utf-8")

            return {
                "url": image_url,  # Оригинал для ссылки
                "base64": f"data:image/jpeg;base64,{base64_encoded}",
                "format": "jpeg",
                "size_bytes": len(optimized_data),
                "dimensions": img.size,
                "original_format": original_format,
            }

        except safe_image_fetcher.ImageFetchError as exc:
            logger.warning("Rejected image for AI analysis: %s", exc.code)
            return {
                "url": image_url,
                "base64": None,
                "error": exc.code,
            }
        except Exception:
            logger.exception("Failed to process image for AI analysis")
            return {
                "url": image_url,
                "base64": None,
                "error": "image_processing_failed",
            }

    def save_processed_image(
        self,
        product_id: int,
        image_data: bytes,
        image_type: str = "optimized",
    ) -> str:
        """
        Сохранить обработанное изображение обратно в R2.
        
        Returns:
            Public URL сохраненного файла
        """
        raw_key = f"{settings.AI_R2_SETTINGS['processed_images_path']}{product_id}/{image_type}.jpg"
        key = get_r2_path(raw_key)
        
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=image_data,
            ContentType="image/jpeg",
            CacheControl="max-age=31536000",  # 1 год кеширования
        )
        
        return f"{self.cdn_url}/{key}"

    def get_product_images_batch(
        self,
        image_urls: List[str],
        max_images: int = 5,
    ) -> List[Dict]:
        """
        Получить батч изображений товара для AI.
        Ограничиваем количество для экономии токенов.
        """
        # Берем первые N изображений (обычно главные)
        selected_urls = image_urls[:max_images]
        
        results = []
        for url in selected_urls:
            processed = self.get_image_for_analysis(url)
            if not processed.get("error"):
                results.append(processed)
        
        return results
