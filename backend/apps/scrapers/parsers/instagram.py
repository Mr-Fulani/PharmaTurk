"""Парсер для Instagram - парсинг постов с медиа и описаниями для товаров."""

import re
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from urllib.parse import urlparse

import instaloader

from ..base.scraper import BaseScraper, ScrapedProduct
from ..base.utils import clean_text


class InstagramParser(BaseScraper):
    """Парсер для Instagram постов.
    
    Парсит медиа (изображения/видео) и описания из Instagram постов
    для дальнейшего отображения в карточках товаров на сайте.
    Изначально предназначен для парсинга книг, но может быть расширен
    для других категорий товаров.
    """
    
    def __init__(self, 
                 base_url="https://www.instagram.com",
                 username: Optional[str] = None,
                 password: Optional[str] = None,
                 **kwargs):
        """Инициализация Instagram парсера.
        
        Args:
            base_url: Базовый URL Instagram
            username: Логин для аутентификации (опционально)
            password: Пароль для аутентификации (опционально)
            **kwargs: Дополнительные параметры для BaseScraper
        """
        super().__init__(
            base_url=base_url,
            delay_range=(5, 10),  # Большие задержки для Instagram
            **kwargs
        )
        
        # Инициализация Instaloader
        self.loader = instaloader.Instaloader(
            download_videos=False,  # Не скачиваем видео на диск
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            post_metadata_txt_pattern='',
            max_connection_attempts=3,
            request_timeout=30.0,
        )
        
        # Аутентификация (опционально)
        self.username = username
        self.password = password
        self._authenticated = False
        
        if username and password:
            self._authenticate()
    
    def _authenticate(self):
        """Аутентификация в Instagram."""
        try:
            self.loader.login(self.username, self.password)
            self._authenticated = True
            self.logger.info(f"Успешная аутентификация для пользователя {self.username}")
        except Exception as e:
            self.logger.warning(f"Ошибка аутентификации: {e}")
            self.logger.info("Продолжаем работу без аутентификации")
    
    def get_name(self) -> str:
        """Возвращает имя парсера."""
        return "instagram"
    
    def get_supported_domains(self) -> List[str]:
        """Возвращает список поддерживаемых доменов."""
        return ["instagram.com", "www.instagram.com"]
    
    def parse_product_list(self, 
                          category_url: str, 
                          max_pages: int = 10) -> List[ScrapedProduct]:
        """Парсит список товаров из профиля Instagram или по хештегу.
        
        Args:
            category_url: URL профиля или хештега Instagram
            max_pages: Максимальное количество постов для парсинга
            
        Returns:
            Список спарсенных товаров
        """
        products = []
        
        try:
            # Определяем тип URL (профиль или хештег)
            if '/explore/tags/' in category_url or '#' in category_url:
                # Парсинг по хештегу
                hashtag = self._extract_hashtag(category_url)
                products = self._parse_hashtag(hashtag, max_pages)
            else:
                # Парсинг профиля
                username = self._extract_username(category_url)
                products = self._parse_profile(username, max_pages)
        
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге списка товаров: {e}")
        
        return products
    
    def parse_product_detail(self, product_url: str) -> Optional[ScrapedProduct]:
        """Парсит детальную информацию о товаре из конкретного поста.
        
        Args:
            product_url: URL поста Instagram
            
        Returns:
            Спарсенный товар или None
        """
        try:
            shortcode = self._extract_shortcode(product_url)
            if not shortcode:
                self.logger.error(f"Не удалось извлечь shortcode из URL: {product_url}")
                return None
            
            post = instaloader.Post.from_shortcode(self.loader.context, shortcode)
            return self._parse_post(post)
        
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге поста {product_url}: {e}")
            return None
    
    def _parse_profile(self, username: str, max_posts: int = 50) -> List[ScrapedProduct]:
        """Парсит посты из профиля пользователя.
        
        Args:
            username: Имя пользователя Instagram
            max_posts: Максимальное количество постов
            
        Returns:
            Список спарсенных товаров
        """
        products = []
        
        try:
            self.logger.info(f"Парсинг профиля @{username}, макс. постов: {max_posts}")
            
            profile = instaloader.Profile.from_username(self.loader.context, username)
            
            for idx, post in enumerate(profile.get_posts()):
                if idx >= max_posts:
                    break
                
                try:
                    product = self._parse_post(post)
                    if product and self.validate_product(product):
                        products.append(product)
                        self.logger.info(f"Спарсен пост {idx + 1}/{max_posts}: {post.shortcode}")
                except Exception as e:
                    self.logger.warning(f"Ошибка при парсинге поста {post.shortcode}: {e}")
                    continue
        
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге профиля @{username}: {e}")
        
        return products
    
    def _parse_hashtag(self, hashtag: str, max_posts: int = 50) -> List[ScrapedProduct]:
        """Парсит посты по хештегу.
        
        Args:
            hashtag: Хештег для поиска (без #)
            max_posts: Максимальное количество постов
            
        Returns:
            Список спарсенных товаров
        """
        products = []
        
        try:
            self.logger.info(f"Парсинг хештега #{hashtag}, макс. постов: {max_posts}")
            
            hashtag_obj = instaloader.Hashtag.from_name(self.loader.context, hashtag)
            
            for idx, post in enumerate(hashtag_obj.get_posts()):
                if idx >= max_posts:
                    break
                
                try:
                    product = self._parse_post(post)
                    if product and self.validate_product(product):
                        products.append(product)
                        self.logger.info(f"Спарсен пост {idx + 1}/{max_posts}: {post.shortcode}")
                except Exception as e:
                    self.logger.warning(f"Ошибка при парсинге поста {post.shortcode}: {e}")
                    continue
        
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге хештега #{hashtag}: {e}")
        
        return products
    
    def _parse_post(self, post: instaloader.Post) -> Optional[ScrapedProduct]:
        """Парсит один пост Instagram и преобразует в ScrapedProduct.
        
        Args:
            post: Объект поста Instaloader
            
        Returns:
            Спарсенный товар или None
        """
        try:
            # Извлекаем caption (описание)
            caption = post.caption or ""
            caption_clean = clean_text(caption)
            
            # Извлекаем название товара из caption
            product_name = self._extract_product_name(caption_clean)
            
            # Собираем все медиа URLs
            images = self._extract_media_urls(post)
            
            # Извлекаем хештеги
            hashtags = self._extract_hashtags(caption)
            
            # Создаем ScrapedProduct
            video_posters = [post.url] if post.is_video and post.url else []

            product = ScrapedProduct(
                name=product_name,
                description=caption_clean,
                url=f"https://www.instagram.com/p/{post.shortcode}/",
                images=images,
                external_id=post.shortcode,
                category="books",  # По умолчанию книги, можно настроить
                is_available=False,  # По умолчанию недоступен, пока не установлена цена
                attributes={
                    'likes': post.likes,
                    'comments': post.comments,
                    'hashtags': hashtags,
                    'post_date': post.date_utc.isoformat() if post.date_utc else None,
                    'owner_username': post.owner_username,
                    'is_video': post.is_video,
                    'video_url': post.video_url if post.is_video else None,
                    'video_posters': video_posters,
                    'raw_caption': caption,  # Сохраняем сырое описание для AI
                },
                source=self.get_name(),
                scraped_at=datetime.now().isoformat(),
            )
            
            return product
        
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге поста: {e}")
            return None
    
    def _extract_product_name(self, caption: str, max_length: int = 50) -> str:
        """Извлекает название товара из описания поста.
        
        Args:
            caption: Текст описания поста
            max_length: Максимальная длина названия
            
        Returns:
            Название товара
        """
        if not caption:
            return "Instagram Post"
        
        # Убираем хештеги и эмодзи для извлечения названия
        text = re.sub(r'#\w+', '', caption)
        text = re.sub(r'@\w+', '', text)
        
        # Ищем название книги - обычно идет после "Цена: 000₽"
        lines = text.split('\n')
        name = ""
        
        for line in lines:
            line = line.strip()
            
            # Если строка содержит "Цена:" в начале, извлекаем текст после цены
            price_match = re.match(r'^Цена[:：]?\s*\d+[₽руб]?\s+(.+)', line, re.IGNORECASE)
            if price_match:
                # Берем текст после цены как название
                name = price_match.group(1).strip()
                break
            
            # Если строка не содержит цену, но это не "Автор:", берем как название
            if line and len(line) > 3:
                if not re.match(r'^Автор[:：]', line, re.IGNORECASE):
                    name = line
                    break
        
        # Если не нашли, берем первое предложение
        if not name:
            sentences = text.split('.')
            if sentences:
                name = sentences[0].strip()
            else:
                name = text.strip()
        
        # Убираем эмодзи и лишние символы
        name = re.sub(r'[^\w\s\-.,!?а-яА-ЯёЁ]', '', name)
        name = name.strip()
        
        # Обрезаем до максимальной длины
        if len(name) > max_length:
            name = name[:max_length].rsplit(' ', 1)[0] + '...'
        
        return name if name else "Instagram Post"
    
    def _extract_media_urls(self, post: instaloader.Post) -> List[str]:
        """Извлекает URLs всех медиа из поста.
        
        Args:
            post: Объект поста Instaloader
            
        Returns:
            Список URLs изображений/видео
        """
        media_urls = []
        
        try:
            # Если это карусель (несколько изображений/видео)
            if post.typename == 'GraphSidecar':
                for node in post.get_sidecar_nodes():
                    # Для всех элементов используем display_url (превью для видео, изображение для фото)
                    media_urls.append(node.display_url)
            # Если это видео - используем превью изображение
            elif post.is_video:
                media_urls.append(post.url)  # post.url - это превью для видео
            # Обычное изображение
            else:
                media_urls.append(post.url)
        
        except Exception as e:
            self.logger.warning(f"Ошибка при извлечении медиа URLs: {e}")
            # Fallback на основное изображение
            if hasattr(post, 'url'):
                media_urls.append(post.url)
        
        return media_urls
    
    def _extract_hashtags(self, caption: str) -> List[str]:
        """Извлекает хештеги из описания.
        
        Args:
            caption: Текст описания поста
            
        Returns:
            Список хештегов (без #)
        """
        if not caption:
            return []
        
        hashtags = re.findall(r'#(\w+)', caption)
        return hashtags
    
    def _extract_username(self, url: str) -> str:
        """Извлекает username из URL профиля.
        
        Args:
            url: URL профиля Instagram
            
        Returns:
            Username
        """
        # Примеры: https://www.instagram.com/username/
        match = re.search(r'instagram\.com/([^/\?]+)', url)
        if match:
            return match.group(1)
        return url
    
    def _extract_hashtag(self, url: str) -> str:
        """Извлекает хештег из URL.
        
        Args:
            url: URL хештега или строка с #
            
        Returns:
            Хештег (без #)
        """
        # Примеры: https://www.instagram.com/explore/tags/books/ или #books
        if url.startswith('#'):
            return url[1:]
        
        match = re.search(r'explore/tags/([^/\?]+)', url)
        if match:
            return match.group(1)
        
        return url
    
    def _extract_shortcode(self, url: str) -> Optional[str]:
        """Извлекает shortcode из URL поста.
        
        Args:
            url: URL поста Instagram
            
        Returns:
            Shortcode или None
        """
        # Примеры: https://www.instagram.com/p/ABC123xyz/
        match = re.search(r'/p/([^/\?]+)', url)
        if match:
            return match.group(1)
        
        # Если передан просто shortcode
        if re.match(r'^[A-Za-z0-9_-]+$', url):
            return url
        
        return None
    
    def validate_product(self, product: ScrapedProduct) -> bool:
        """Валидирует спарсенный товар.
        
        Args:
            product: Товар для валидации
            
        Returns:
            True если товар валиден
        """
        # Базовая валидация от родительского класса
        if not super().validate_product(product):
            return False
        
        # Проверяем наличие медиа
        if not product.images or len(product.images) == 0:
            self.logger.warning(f"Товар {product.name} без изображений")
            return False
        
        # Проверяем наличие описания
        if not product.description or len(product.description.strip()) < 10:
            self.logger.warning(f"Товар {product.name} без описания или слишком короткое")
            return False
        
        return True
