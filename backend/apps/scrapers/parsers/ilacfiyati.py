"""Парсер для сайта ilacfiyati.com (лекарства и добавки)."""

import logging
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from ..base.scraper import BaseScraper, ScrapedProduct
from ..base.utils import clean_text, normalize_price, extract_currency


class IlacFiyatiParser(BaseScraper):
    """Парсер для сайта ilacfiyati.com."""

    def get_name(self) -> str:
        """Возвращает уникальное имя парсера."""
        return "ilacfiyati"

    def get_supported_domains(self) -> List[str]:
        """Возвращает список поддерживаемых доменов."""
        return ["ilacfiyati.com", "www.ilacfiyati.com"]

    def parse_product_list(self, category_url: str, max_pages: int = 10) -> List[ScrapedProduct]:
        """
        Парсит список товаров из указанной категории.
        Поддерживает пагинацию через параметр `?pg=`.
        """
        products = []
        page = 1
        
        try:
            self.logger.info(f"Начинаем парсинг товаров: {category_url}")
            
            while page <= max_pages:
                url = f"{category_url}?pg={page}" if page > 1 else category_url
                self.logger.info(f"Запрос страницы {page}: {url}")
                
                html = self._make_request(url)
                if not html:
                    break

                soup = BeautifulSoup(html, 'html.parser')
                
                # Ищем все ссылки на товары. 
                # Исходя из структуры, ссылки на товары содержат /ilaclar/ или /takviye-edici-gida/
                product_links = soup.select('a[href*="/ilaclar/"], a[href*="/takviye-edici-gida/"]')
                product_urls = []
                
                for link in product_links:
                    href = link.get('href')
                    # Отсекаем ссылки на пагинацию или категории
                    if href and 'pg=' not in href:
                        path = urlparse(href).path.strip('/')
                        path_parts = path.split('/')
                        if len(path_parts) >= 2 and path_parts[0] in ('ilaclar', 'takviye-edici-gida'):
                            full_url = urljoin(self.base_url, href)
                            if full_url not in product_urls:
                                product_urls.append(full_url)
                
                if not product_urls:
                    self.logger.info("Ссылки на товары не найдены, завершаем пагинацию.")
                    break
                    
                for product_url in product_urls:
                    if self.max_products and len(products) >= self.max_products:
                        return products
                        
                    detail = self.parse_product_detail(product_url)
                    if detail and self.validate_product(detail):
                        products.append(detail)
                        
                page += 1
                
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге списка товаров: {e}")
            
        return products

    def parse_product_detail(self, product_url: str) -> Optional[ScrapedProduct]:
        """
        Парсит детальную страницу товара.
        Извлекает название, цену и характеристики.
        """
        try:
            self.logger.info(f"Парсинг деталей товара: {product_url}")
            html = self._make_request(product_url)
            if not html:
                return None

            soup = BeautifulSoup(html, 'html.parser')
            
            # 1. Название товара (чаще в h1 или в .font-size-22.text-primary.fw-bold)
            title_elem = soup.select_one('.product-name, h1, h2, .font-size-22.text-primary.fw-bold, .title')
            name = ""
            if title_elem:
                for content in title_elem.contents:
                    if isinstance(content, str) and content.strip():
                        name = clean_text(content)
                        break
                if not name:
                    name = clean_text(title_elem.text)
            
            if not name:
                self.logger.warning(f"Не удалось найти название на странице {product_url}")
                return None

            # 2. Цена
            # На ilacfiyati.com цена в строке таблицы İLAÇ FİYATI: "164,22 TL"
            price = None
            # Сначала пробуем найти напрямую в таблице по ключу (самый точный способ)
            for row in soup.find_all('tr'):
                cols = row.find_all(['th', 'td'])
                if len(cols) == 2:
                    key_raw = cols[0].text.strip().lower()
                    if 'fiyat' in key_raw and 'kamu' not in key_raw:
                        price = normalize_price(cols[1].text)
                        if price:
                            break
            # Запасной вариант: ищем в тексте по символу ₺ или слову TL
            if not price:
                price_tags = soup.find_all(text=lambda x: x and ('₺' in x or ' TL' in x))
                for text_node in price_tags:
                    text_clean = text_node.strip()
                    if any(char.isdigit() for char in text_clean):
                        price = normalize_price(text_clean)
                        if price:
                            break
            

            # 3. Дополнительные атрибуты (таблицы, характеристики)
            attributes = {}
            description_lines = []
            brand = ""  # Бренд/производитель для ScrapedProduct.brand
            
            # Собираем данные из таблиц, если они есть
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cols = row.find_all(['th', 'td'])
                    if len(cols) == 2:
                        key = clean_text(cols[0].text).lower()
                        val = clean_text(cols[1].text)
                        
                        if 'barkod' in key or 'barcode' in key:
                            attributes['barcode'] = val
                        elif 'fi̇rma' in key or 'firma' in key or 'manufacturer' in key:
                            # Название фирмы → бренд товара (Fi̇RMA ADI.lower() = 'fi̇rma adi')
                            if not brand:
                                brand = val
                        elif 'atc' in key:
                            attributes['atc_code'] = val
                        elif 'etki̇n madde kodu' in key or 'etkin madde kodu' in key:
                            attributes['sgk_active_ingredient_code'] = val
                        elif 'etki̇n madde' in key or 'etkin madde' in key:
                            # Действующее вещество: ETKİN MADDE → 'etki̇n madde', но НЕ 'SGK ETKİN MADDE KODU'
                            if 'kodu' not in key and 'active_ingredient' not in attributes:
                                attributes['active_ingredient'] = val
                        elif 'reçete' in key:
                            attributes['prescription_type'] = val
                            if 'reçetesiz' not in val.lower() and val.lower().strip() != '-':
                                attributes['prescription_required'] = True
                        elif 'ambalaj' in key or 'miktar' in key:
                            attributes['volume'] = val
                        elif 'formu' in key:
                            # Маппинг турецких форм выпуска на наши choices-коды
                            val_lower = val.lower()
                            if 'tablet' in val_lower or 'film' in val_lower:
                                attributes['dosage_form'] = 'tablet'
                            elif 'kapsül' in val_lower or 'kapsul' in val_lower:
                                attributes['dosage_form'] = 'capsule'
                            elif 'şurup' in val_lower or 'surup' in val_lower:
                                attributes['dosage_form'] = 'syrup'
                            elif 'damla' in val_lower:
                                attributes['dosage_form'] = 'drops'
                            elif 'merhem' in val_lower or 'pomad' in val_lower:
                                attributes['dosage_form'] = 'ointment'
                            elif 'krem' in val_lower or 'cream' in val_lower:
                                attributes['dosage_form'] = 'cream'
                            elif 'jel' in val_lower or 'gel' in val_lower:
                                attributes['dosage_form'] = 'gel'
                            elif 'ampul' in val_lower or 'enjeksiyon' in val_lower or 'flakon' in val_lower:
                                attributes['dosage_form'] = 'injection'
                            elif 'toz' in val_lower or 'granül' in val_lower:
                                attributes['dosage_form'] = 'powder'
                            elif 'sprey' in val_lower or 'spray' in val_lower or 'inhaler' in val_lower:
                                attributes['dosage_form'] = 'spray'
                            elif 'supozit' in val_lower:
                                attributes['dosage_form'] = 'suppository'
                            else:
                                attributes['dosage_form'] = 'other'
                            # Сохраняем исходное турецкое значение как дополнительный атрибут для AI
                            attributes['dosage_form_raw'] = val
                        elif 'menşei' in key:
                            attributes['origin_country'] = val
                        elif 'sgk ödeme' in key:
                            # Статус оплаты SGK (первое совпадение)
                            if 'sgk_status' not in attributes:
                                attributes['sgk_status'] = val
                        elif 'eşdeğer kodu' in key or 'esdeger kodu' in key:
                            attributes['sgk_equivalent_code'] = val
                        elif 'kamu no' in key:
                            attributes['sgk_public_no'] = val
                        elif 'uygulama' in key:
                            attributes['administration_route'] = val
                        elif 'raf ömrü' in key:
                            attributes['shelf_life'] = val
                        elif 'saklama' in key:
                            attributes['storage_conditions'] = val
                        elif 'nfc' in key:
                            attributes['nfc_code'] = val
                        elif 'özel' in key or 'ozel' in key:
                            attributes['special_notes'] = val

                        description_lines.append(f"{cols[0].text.strip()}: {val}")
            
            # Дополнительно вытаскиваем вкладки с описанием (Ne İçin Kullanılır, Yan Etkileri, и др.)
            tabs_content = soup.select('.tab-content, .panel-body, #ozet, #kullanim, #yan-etkiler')
            for tab in tabs_content:
                text = clean_text(tab.text)
                if text:
                    description_lines.append(text)
            
            # Формируем сырое описание из таблиц и вкладок для последующей AI обработки
            description = "\n\n".join(description_lines)
            
            # 4. Изображения
            images = []
            # Пробуем найти og:image как главное
            og_img = soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                images.append(urljoin(self.base_url, og_img["content"]))
                
            img_tags = soup.select(".swiper-slide img[src], img[src]")
            for img in img_tags:
                src = img.get("src")
                if not src:
                    continue
                src_lower = src.lower()
                
                # Товарные картинки обычно лежат в /dosyalar/ (исключая /dosyalar/site/ - где логотип)
                # Исключаем UI картинки типа svg, shadow.png, app-store.webp
                is_product_img = (
                    ("dosyalar" in src_lower and "site" not in src_lower) or 
                    ("urun" in src_lower) or 
                    ("resim" in src_lower and "assets" not in src_lower)
                )
                is_valid_extension = not src_lower.endswith(".svg") and "shadow" not in src_lower and "app-store" not in src_lower and "google-play" not in src_lower

                if is_product_img and is_valid_extension:
                    full_img_url = urljoin(self.base_url, src)
                    if full_img_url not in images:
                        images.append(full_img_url)

            # Внешний ID берём из URL
            external_id = product_url.rstrip("/").split("/")[-1]
            if not external_id:
                external_id = name

            return ScrapedProduct(
                name=name,
                description=description,
                price=price,
                currency="TRY",         # На сайте цены в турецких лирах
                url=product_url,
                images=images,
                external_id=external_id,
                brand=brand,            # Производитель из поля FİRMA ADI
                barcode=attributes.get('barcode', ''),
                is_available=True,      # Считаем, что товар доступен (так как сайт информационный)
                stock_quantity=3,       # Дефолтное значение
                source=self.get_name(),
                attributes=attributes
            )
            
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге детальной страницы {product_url}: {e}")
            return None
