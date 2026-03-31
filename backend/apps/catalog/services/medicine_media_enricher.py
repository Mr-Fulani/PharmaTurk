import logging
import io
from typing import List, Optional

import httpx
from PIL import Image
import imagehash
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.cache import cache
from django.db import models

from django.utils import timezone
from apps.catalog.models import MediaEnrichmentStatus

logger = logging.getLogger(__name__)


class OpenFoodFactsClient:
    """Client for fetching images from Open Food Facts API using barcode."""
    
    BASE_URL = "https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    
    def fetch_images(self, barcode: str) -> List[str]:
        if not barcode:
            return []
            
        url = self.BASE_URL.format(barcode=barcode)
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
                
                if data.get("status") != 1:
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
                response.raise_for_status()
                data = response.json()
                
                # Serper returns a list of images under the "images" key
                urls = [item.get("imageUrl") for item in data.get("images", []) if item.get("imageUrl")]
                return urls
        except Exception as e:
            logger.error("Error fetching from Serper Image Search for query '%s': %s", query, e)
            return []


class MedicineMediaEnricher:
    """Service to enrich MedicineProduct with images from external sources."""
    
    def __init__(self):
        self.open_food_facts_client = OpenFoodFactsClient()
        self.serper_client = SerperImageSearchClient()
        self.min_width = settings.MEDICINE_MEDIA_MIN_WIDTH
        self.min_height = settings.MEDICINE_MEDIA_MIN_HEIGHT
        
    def build_search_queries(self, product: models.Model) -> List[str]:
        queries = []
        name = product.name or ""
        active_ingredient = getattr(product, 'active_ingredient', "")
        
        if name and active_ingredient:
            queries.append(f"{name} {active_ingredient}")
            
        if name:
            queries.append(name)
            
        # Add ATC code context if available
        atc_code = getattr(product, 'atc_code', "")
        if atc_code and name:
            queries.append(f"{name} {atc_code}")
            
        return list(dict.fromkeys(queries))  # Remove duplicates preserving order

    def fetch_candidates(self, product: models.Model) -> List[str]:
        urls = []
        
        # 1. Open Food Facts
        barcode = getattr(product, 'barcode', getattr(product, 'gtin', ''))
        if barcode:
            logger.info("Product %s has barcode %s. Searching in Open Food Facts...", product.id, barcode)
            off_urls = self.open_food_facts_client.fetch_images(barcode)
            urls.extend(off_urls)
            logger.info("Open Food Facts returned %d candidates for product %s.", len(off_urls), product.id)
        else:
            logger.info("Product %s has no barcode. Skipping Open Food Facts.", product.id)
            
        # 2. Serper Image Search
        if settings.SERPER_API_KEY:
            queries = self.build_search_queries(product)
            logger.info("Searching in Serper Image Search with queries: %s", queries)
            for query in queries:
                serper_urls = self.serper_client.fetch_images(query)
                logger.info("Serper Image Search returned %d candidates for query '%s'.", len(serper_urls), query)
                urls.extend(serper_urls)
                if len(urls) >= 10:  # Cap candidates to avoid excessive requests
                    logger.info("Reached maximum candidate limit (10). Stopping Serper search.")
                    break
        else:
            logger.info("SERPER_API_KEY is not set. Skipping Serper Image Search.")
                    
        return list(dict.fromkeys(urls))

    def validate_image(self, url: str) -> bool:
        logger.info("Validating image candidate: %s", url)
        try:
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                with client.stream("GET", url) as response:
                    # Check Content-Length if available
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > 10 * 1024 * 1024:  # 10 MB limit
                        logger.warning("Image %s is too large (%s bytes). Max allowed is 10MB.", url, content_length)
                        return False
                    
                    response.read()
                    response.raise_for_status()
                    
                    image_data = response.content
                    with Image.open(io.BytesIO(image_data)) as img:
                        width, height = img.size
                        if width >= self.min_width and height >= self.min_height:
                            logger.info("Image %s is valid. Size: %dx%d.", url, width, height)
                            return True
                        else:
                            logger.warning("Image %s is too small (%dx%d). Required minimum is %dx%d.", 
                                           url, width, height, self.min_width, self.min_height)
            return False
        except Exception as e:
            logger.warning("Image validation failed for %s: %s", url, e)
            return False

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

    def download_and_save(self, product: models.Model, url: str) -> Optional[models.Model]:
        try:
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
                
                image_data = response.content
                
                # Calculate perceptual hash to detect duplicates
                current_hash = self.get_image_hash(image_data)
                
                if current_hash:
                    # Check against existing images (compute their hash if missing)
                    existing_images = product.gallery_images.all()
                    for ext_img in existing_images:
                        ext_hash = ext_img.image_hash
                        # If existing image doesn't have a hash, try to compute and save it
                        if not ext_hash and ext_img.image_file:
                            try:
                                with ext_img.image_file.open('rb') as f:
                                    ext_hash = self.get_image_hash(f.read())
                                    if ext_hash:
                                        ext_img.image_hash = ext_hash
                                        ext_img.save(update_fields=['image_hash'])
                            except Exception as e:
                                logger.warning("Could not compute hash for existing image %s: %s", ext_img.id, e)
                        
                        if ext_hash:
                            # If difference between hashes is small (< 10), images are visually identical
                            if imagehash.hex_to_hash(current_hash) - imagehash.hex_to_hash(ext_hash) < 10:
                                logger.info("Image %s is visually identical to existing image %s (hash match). Skipping.", url, ext_img.id)
                                return None
                
                # Check if product has a main image
                has_main = product.gallery_images.filter(is_main=True).exists()
                
                # Create the image record
                filename = url.split("/")[-1].split("?")[0]
                if not filename or "." not in filename:
                    filename = f"product_{product.id}_image.jpg"
                # Узнаем модель картинки из связанных полей
                ImageModel = product.gallery_images.model
                
                image_record = ImageModel(
                    product=product,
                    image_url=url,
                    is_main=not has_main,
                    image_hash=current_hash
                )
                image_record.image_file.save(filename, ContentFile(image_data), save=False)
                image_record.save()
                
                logger.info("Successfully downloaded and saved image %s for product %s.", url, product.id)
                return image_record
        except Exception as e:
            logger.error("Failed to download and save image %s for product %s: %s", url, product.id, e)
            return None

    def enrich(self, product: models.Model, max_images: int, ignore_cache: bool = False) -> int:
        logger.info("Starting enrichment for product ID: %s (Name: '%s')", product.id, product.name)
        current_count = product.gallery_images.count()
        if current_count >= max_images:
            logger.info("Product %s already has %d images (max %d). Skipping.", product.id, current_count, max_images)
            return 0
            
        # Check cache to avoid hitting APIs if we already tried and failed recently
        cache_key = f"medicine_media_enrich_failed_{product.id}"
        if not ignore_cache and cache.get(cache_key):
            logger.info("Product %s is in failed cache (no images found recently). Skipping to save API limits.", product.id)
            return 0
            
        from django.db import transaction
        
        try:
            with transaction.atomic():
                product.media_enrichment_status = MediaEnrichmentStatus.PROCESSING
                product.save(update_fields=['media_enrichment_status'])
        except Exception as e:
             logger.error("Failed to set early processing status for product %s: %s", product.id, e)
            
        try:
            candidates = self.fetch_candidates(product)
            if not candidates:
                logger.info("No candidates found for product %s. Caching failure for 7 days.", product.id)
                cache.set(cache_key, True, timeout=604800)
                
                product.media_enrichment_status = MediaEnrichmentStatus.COMPLETED
                product.media_enrichment_last_at = timezone.now()
                product.media_enrichment_error = "Изображений не найдено"
                product.save(update_fields=['media_enrichment_status', 'media_enrichment_last_at', 'media_enrichment_error'])
                return 0
                
            added_count = 0
            for url in candidates:
                if current_count + added_count >= max_images:
                    logger.info("Reached target image count (%d) for product %s.", max_images, product.id)
                    break
                    
                if product.gallery_images.filter(image_url=url).exists():
                    logger.info("URL %s is already attached to product %s. Skipping.", url, product.id)
                    continue
                    
                if self.validate_image(url):
                    saved_image = self.download_and_save(product, url)
                    if saved_image:
                        added_count += 1
                        
            if added_count == 0:
                logger.info("Candidates were found but none were valid/saved. Caching failure for 7 days.")
                cache.set(cache_key, True, timeout=604800)
                product.media_enrichment_error = "Valid candidates not found"
            else:
                product.media_enrichment_error = None
                
            product.media_enrichment_status = MediaEnrichmentStatus.COMPLETED
            product.media_enrichment_last_at = timezone.now()
            product.save(update_fields=['media_enrichment_status', 'media_enrichment_last_at', 'media_enrichment_error'])
            
            logger.info("Finished enrichment for product %s. Added %d new images.", product.id, added_count)
            return added_count
            
        except Exception as e:
            logger.exception("Catastrophic failure during enrichment for product %s: %s", product.id, e)
            product.media_enrichment_status = MediaEnrichmentStatus.FAILED
            product.media_enrichment_error = str(e)
            product.media_enrichment_last_at = timezone.now()
            product.save(update_fields=['media_enrichment_status', 'media_enrichment_last_at', 'media_enrichment_error'])
            return 0
