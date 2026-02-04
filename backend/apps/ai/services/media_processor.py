import boto3
import requests
from PIL import Image
from io import BytesIO
from typing import List, Dict, Optional
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class R2MediaProcessor:
    """
    Обработка медиафайлов из R2 для AI сервисов.
    Оптимизация изображений перед отправкой в Vision API.
    """
    def __init__(self):
        self.s3 = boto3.client(
            's3',
            endpoint_url=settings.R2_CONFIG['endpoint_url'],
            aws_access_key_id=settings.R2_CONFIG['aws_access_key_id'],
            aws_secret_access_key=settings.R2_CONFIG['aws_secret_access_key'],
            region_name=settings.R2_CONFIG['region_name']
        )
        self.bucket = settings.R2_CONFIG['bucket_name']
        self.cdn_url = settings.AI_R2_SETTINGS['cdn_url']

    def get_image_for_analysis(
        self,
        image_url: str,
        max_size: tuple = (1024, 1024),
        quality: int = 85
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
            # Скачиваем изображение
            if image_url.startswith(self.cdn_url):
                # Из R2 - прямой доступ
                key = image_url.replace(f"{self.cdn_url}/", "")
                response = self.s3.get_object(Bucket=self.bucket, Key=key)
                image_data = response['Body'].read()
            else:
                # Внешний URL
                response = requests.get(image_url, timeout=30)
                response.raise_for_status()
                image_data = response.content
            
            # Оптимизация
            img = Image.open(BytesIO(image_data))
            original_format = img.format
            
            # Конвертация в RGB если нужно
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            # Resize с сохранением пропорций
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Сохранение в буфер
            buffer = BytesIO()
            img.save(buffer, format='JPEG', quality=quality, optimize=True)
            buffer.seek(0)
            
            optimized_data = buffer.getvalue()
            
            # Base64 для OpenAI Vision API
            import base64
            base64_encoded = base64.b64encode(optimized_data).decode('utf-8')
            
            return {
                'url': image_url,  # Оригинал для ссылки
                'base64': f"data:image/jpeg;base64,{base64_encoded}",
                'format': 'jpeg',
                'size_bytes': len(optimized_data),
                'dimensions': img.size,
                'original_format': original_format
            }
            
        except Exception as e:
            logger.error(f"Error processing image {image_url}: {e}")
            return {
                'url': image_url,
                'base64': None,
                'error': str(e)
            }

    def save_processed_image(
        self,
        product_id: int,
        image_data: bytes,
        image_type: str = 'optimized'
    ) -> str:
        """
        Сохранить обработанное изображение обратно в R2.
        
        Returns:
            Public URL сохраненного файла
        """
        key = f"{settings.AI_R2_SETTINGS['processed_images_path']}{product_id}/{image_type}.jpg"
        
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=image_data,
            ContentType='image/jpeg',
            CacheControl='max-age=31536000'  # 1 год кеширования
        )
        
        return f"{self.cdn_url}/{key}"

    def get_product_images_batch(
        self,
        image_urls: List[str],
        max_images: int = 5
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
            if not processed.get('error'):
                results.append(processed)
        
        return results
