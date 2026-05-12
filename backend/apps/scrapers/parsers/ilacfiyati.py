"""Парсер для сайта ilacfiyati.com (лекарства и добавки)."""

import logging
import re
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from ..base.scraper import BaseScraper, ScrapedProduct
from ..base.utils import clean_text, normalize_price, extract_currency


class IlacFiyatiParser(BaseScraper):
    """Парсер для сайта ilacfiyati.com."""

    DETAIL_TABS = {
        "ilac_bilgileri": {
            "path": "ilac-bilgileri",
            "title": "İlaç Bilgileri",
            "keywords": ("İLAÇ BİLGİLERİ", "ILAC BILGILERI"),
        },
        "equivalents": {
            "path": "esdegeri",
            "title": "Eşdeğeri",
            "keywords": ("EŞDEĞER", "ESDEGER"),
        },
        "sgk_equivalents": {
            "path": "sgk-esdegeri",
            "title": "SGK Eşdeğeri",
            "keywords": ("SGK EŞDEĞER", "SGK ESDEGER"),
        },
        "summary": {
            "path": "ozet",
            "title": "Özet",
            "keywords": ("KULLANMA TALİMATI", "KULLANMA TALIMATI", "ÖZET", "OZET"),
        },
        "indications": {
            "path": "ne-icin-kullanilir",
            "title": "Ne İçin Kullanılır",
            "keywords": ("NE İÇİN KULLANILIR", "NE ICIN KULLANILIR"),
        },
        "before_use_warnings": {
            "path": "kullanmadan-dikkat-edilecekler",
            "title": "Kullanmadan Dikkat Edilecekler",
            "keywords": ("KULLANMADAN ÖNCE", "KULLANMADAN ONCE", "DİKKAT EDİLMESİ", "DIKKAT EDILMESI"),
        },
        "usage_instructions": {
            "path": "nasil-kullanilir",
            "title": "Nasıl Kullanılır",
            "keywords": ("NASIL KULLANILIR",),
        },
        "side_effects": {
            "path": "yan-etkileri",
            "title": "Yan Etkileri",
            "keywords": ("YAN ETKİLER", "YAN ETKILER"),
        },
        "storage_conditions": {
            "path": "saklanmasi",
            "title": "Saklanması",
            "keywords": ("SAKLANMASI", "NASIL SAKLANIR"),
        },
    }

    NOISE_MARKERS = (
        "İlaç Hasta Payı Hesapla",
        "Reçeteye Ekle",
        "İlaç Katılım Payı Hesaplama",
        "Perakende Satış Fiyatı",
        "Hasta İlaç Katılım Payı",
        "Eczaneye Ödenecek Tutar",
        "Maaştan Kesilecek Tutar",
        "Hemen İndirin",
        "UYARI: Bu sitede yer alan bilgilerin kullanılmasının sorumluluğu",
        "Copyright ©",
        "Sitemizde yer alan içerik bilgi amaçlı",
    )

    def get_name(self) -> str:
        """Возвращает уникальное имя парсера."""
        return "ilacfiyati"

    def get_supported_domains(self) -> List[str]:
        """Возвращает список поддерживаемых доменов."""
        return ["ilacfiyati.com", "www.ilacfiyati.com"]

    @staticmethod
    def _normalize_tr_key(value: str) -> str:
        normalized = (value or "").strip().upper()
        replacements = {
            "İ": "I",
            "İ": "I",
            "ı": "I",
            "Ğ": "G",
            "Ü": "U",
            "Ş": "S",
            "Ö": "O",
            "Ç": "C",
        }
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
        return re.sub(r"\s+", " ", normalized)

    def _canonical_product_url(self, product_url: str) -> str:
        parsed = urlparse(product_url)
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(parts) >= 3 and parts[0] in ("ilaclar", "takviye-edici-gida"):
            parts = parts[:2]
        path = "/" + "/".join(parts)
        return parsed._replace(path=path, params="", query="", fragment="").geturl().rstrip("/")

    def _clean_tab_text(self, text: str) -> str:
        text = str(text or "").strip()
        if not text:
            return ""
        kept = []
        for line in re.split(r"\n+|(?<=\.)\s{2,}", text):
            line = clean_text(line)
            if not line:
                continue
            if any(marker.lower() in line.lower() for marker in self.NOISE_MARKERS):
                break
            if line in {"KAPAT", "Evet", "Çalışan", "Emekli", "İlaç Adedi"}:
                continue
            kept.append(line)
        text = "\n".join(kept)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text[:12000]

    def _extract_tab_text(self, soup: BeautifulSoup, tab_key: str) -> str:
        tab = self.DETAIL_TABS.get(tab_key) or {}
        keywords = tuple(self._normalize_tr_key(k) for k in tab.get("keywords", ()))

        for selector in ("script", "style", "nav", "header", "footer", "form", "input", "select", "button"):
            for node in soup.select(selector):
                node.decompose()

        headings = soup.find_all(["h1", "h2", "h3", "h4", "h5"])
        start = None
        for heading in headings:
            heading_text = self._normalize_tr_key(heading.get_text(" ", strip=True))
            if any(keyword and keyword in heading_text for keyword in keywords):
                start = heading
                break

        if start is not None:
            chunks = [start.get_text("\n", strip=True)]
            for sibling in start.next_siblings:
                if getattr(sibling, "name", None) in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                    sibling_text = sibling.get_text(" ", strip=True)
                    if "İlaç Katılım Payı" in sibling_text or "Ilac Katilim Payi" in self._normalize_tr_key(sibling_text):
                        break
                if hasattr(sibling, "get_text"):
                    text = sibling.get_text("\n", strip=True)
                else:
                    text = str(sibling).strip()
                if text:
                    chunks.append(text)
            extracted = self._clean_tab_text("\n".join(chunks))
            if extracted:
                return extracted

        body = soup.body or soup
        text = body.get_text("\n", strip=True)
        lines = []
        seen_title = False
        for raw_line in text.splitlines():
            line = clean_text(raw_line)
            if not line:
                continue
            norm = self._normalize_tr_key(line)
            if any(keyword and keyword in norm for keyword in keywords):
                seen_title = True
            if seen_title:
                lines.append(line)
            if seen_title and "ILAC KATILIM PAYI" in norm:
                break
        return self._clean_tab_text("\n".join(lines))

    def _fetch_detail_tabs(self, product_url: str) -> Dict[str, Dict[str, str]]:
        base_url = self._canonical_product_url(product_url)
        tabs: Dict[str, Dict[str, str]] = {}
        for key, tab in self.DETAIL_TABS.items():
            tab_url = f"{base_url}/{tab['path']}"
            try:
                html = self._make_request(tab_url)
                if not html:
                    continue
                soup = BeautifulSoup(html, "html.parser")
                text = self._extract_tab_text(soup, key)
                if text:
                    tabs[key] = {
                        "title": tab["title"],
                        "url": tab_url,
                        "text": text,
                    }
            except Exception as e:
                self.logger.warning(f"Не удалось получить вкладку {tab['path']} для {product_url}: {e}")
        return tabs

    @staticmethod
    def _extract_external_id_from_url(url: str) -> str:
        parsed = urlparse(url or "")
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(parts) >= 2 and parts[0] in ("ilaclar", "takviye-edici-gida"):
            return parts[1]
        return parts[-1] if parts else ""

    def _extract_analog_codes(self, text: str) -> Dict[str, str]:
        text = clean_text(text or "")
        codes: Dict[str, str] = {}

        barcode_match = re.search(r"\b(\d{13})\b", text)
        if barcode_match:
            codes["barcode"] = barcode_match.group(1)

        atc_match = re.search(r"\b([A-Z]\d{2}[A-Z]{2}\d{2})\b", text.upper())
        if atc_match:
            codes["atc_code"] = atc_match.group(1)

        sgk_match = re.search(r"\b(E\d{3,}[A-Z]?)\b", text.upper())
        if sgk_match:
            codes["sgk_equivalent_code"] = sgk_match.group(1)

        return codes

    def _extract_analog_from_link(
        self,
        link,
        *,
        current_product_url: str,
        source_tab: str,
    ) -> Optional[Dict[str, Any]]:
        href = link.get("href", "")
        if "/ilaclar/" not in href or any(x in href for x in ["#", "?"]):
            return None

        analog_url = urljoin(self.base_url, href)
        url_path = urlparse(analog_url).path.strip("/")
        path_segments = [s for s in url_path.split("/") if s]
        if len(path_segments) != 2:
            return None

        if analog_url.rstrip("/") == current_product_url.rstrip("/"):
            return None

        analog_name = clean_text(link.text)
        norm_name = analog_name.lower().replace("i̇", "i").replace("ı", "i").strip()
        ignore_names = {
            "ilaç bilgileri", "ilac bilgileri", "ilaç sınıfı", "ilac sinifi",
            "sgk ödeme durumu", "sgk odeme durumu", "reçete kuralı", "recete kurali",
            "sut açıklama", "sut aciklama", "aç-tok bilgisi", "ac-tok bilgisi",
            "besin etkileşimi", "besin etkilesimi", "özet", "ozet",
            "ne için kullanılır", "ne icin kullanilir", "yan etkileri",
            "saklanması", "saklanmasi", "kullanma talimatı", "kullanma talimati",
            "kısa ürün bilgisi", "kisa urun bilgisi", "eşdeğeri", "esdegeri",
            "sgk eşdeğeri", "sgk esdegeri",
        }
        if len(norm_name) < 3 or norm_name in ignore_names:
            return None

        row = link.find_parent("tr")
        context = row.get_text(" ", strip=True) if row else link.parent.get_text(" ", strip=True)
        analog = {
            "name": analog_name,
            "url": analog_url,
            "price": normalize_price(context) if "TL" in context or "₺" in context else None,
            "external_id": self._extract_external_id_from_url(analog_url),
            "source_tab": source_tab,
        }
        analog.update(self._extract_analog_codes(context))
        return analog

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
            self.logger.error(f"Ошибка при парсимге списка товаров: {e}")
            
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
            
            # 1. Название товара
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
            price = None
            for row in soup.find_all('tr'):
                cols = row.find_all(['th', 'td'])
                if len(cols) == 2:
                    key_raw = cols[0].text.strip().lower()
                    if 'fiyat' in key_raw and 'kamu' not in key_raw:
                        price = normalize_price(cols[1].text)
                        if price:
                            break
            if not price:
                price_tags = soup.find_all(text=lambda x: x and ('\u20BA' in x or ' TL' in x))
                for text_node in price_tags:
                    text_clean = text_node.strip()
                    if any(char.isdigit() for char in text_clean):
                        price = normalize_price(text_clean)
                        if price:
                            break
            

            # 3. Дополнительные атрибуты (таблицы, характеристики)
            attributes = {}
            description_lines = []
            brand = ""
            
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cols = row.find_all(['th', 'td'])
                    if len(cols) == 2:
                        key = clean_text(cols[0].text).lower()
                        val = clean_text(cols[1].text)
                        
                        # Сопоставление ключей (игнорируем точки над i и специфику турецкого lower())
                        key_norm = key.replace('i̇', 'i').replace('\u0131', 'i').replace('i', 'i')
                        
                        if 'barkod' in key_norm or 'barcode' in key_norm:
                            attributes['barcode'] = val
                        elif ('fi' in key_norm and 'rma' in key_norm) or 'manufacturer' in key_norm:
                            if not brand:
                                brand = val
                        elif 'atc' in key_norm:
                            attributes['atc_code'] = val
                        elif 'etki' in key_norm and 'madde' in key_norm and 'kodu' in key_norm:
                            attributes['sgk_active_ingredient_code'] = val
                        elif 'etki' in key_norm and 'madde' in key_norm:
                            if 'kodu' not in key_norm:
                                # Действующее вещество
                                if 'active_ingredient' not in attributes:
                                    attributes['active_ingredient'] = val
                        elif 're\u00e7ete' in key_norm or 'recete' in key_norm:
                            attributes['prescription_type'] = val
                            if 're\u00e7etesiz' not in val.lower() and val.lower().strip() != '-':
                                attributes['prescription_required'] = True
                        elif 'ambalaj' in key_norm or 'miktar' in key_norm:
                            attributes['volume'] = val
                        elif 'formu' in key_norm:
                            val_lower = val.lower()
                            if 'tablet' in val_lower or 'film' in val_lower:
                                attributes['dosage_form'] = 'tablet'
                            elif 'kaps\u00fcl' in val_lower or 'kapsul' in val_lower:
                                attributes['dosage_form'] = 'capsule'
                            elif '\u015furup' in val_lower or 'surup' in val_lower:
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
                            elif 'toz' in val_lower or 'gran\u00fcl' in val_lower:
                                attributes['dosage_form'] = 'powder'
                            elif 'sprey' in val_lower or 'spray' in val_lower or 'inhaler' in val_lower:
                                attributes['dosage_form'] = 'spray'
                            elif 'supozit' in val_lower:
                                attributes['dosage_form'] = 'suppository'
                            else:
                                attributes['dosage_form'] = 'other'
                            attributes['dosage_form_raw'] = val
                        elif 'men\u015fei' in key_norm or 'mensei' in key_norm:
                            attributes['origin_country'] = val
                        elif 'sgk' in key_norm and ('\u00f6deme' in key_norm or 'odeme' in key_norm or 'fiyat' in key_norm):
                            if 'sgk_status' not in attributes:
                                attributes['sgk_status'] = val
                        elif 'e\u015fde\u011fer kodu' in key_norm or 'esdeger kodu' in key_norm:
                            attributes['sgk_equivalent_code'] = val
                        elif 'kamu no' in key_norm:
                            attributes['sgk_public_no'] = val
                        elif 'uygulama' in key_norm:
                            attributes['administration_route'] = val
                        elif 'raf \u00f6mr\u00fc' in key_norm or 'raf omru' in key_norm:
                            attributes['shelf_life'] = val
                        elif 'saklama' in key_norm:
                            attributes['storage_conditions'] = val
                        elif 'nfc' in key_norm:
                            attributes['nfc_code'] = val
                        elif '\u00f6zel' in key_norm or 'ozel' in key_norm:
                            attributes['special_notes'] = val

                        description_lines.append(f"{cols[0].text.strip()}: {val}")
            
            # 4. Вкладки инструкции препарата.
            # ilacfiyati держит важные разделы на отдельных URL вида /{slug}/nasil-kullanilir.
            # Сохраняем турецкий source структурированно, чтобы AI только переводил, а не додумывал.
            detail_tabs = self._fetch_detail_tabs(product_url)
            if detail_tabs:
                attributes["source_tabs"] = detail_tabs
                description_tab_order = (
                    "summary",
                    "indications",
                    "before_use_warnings",
                    "usage_instructions",
                    "side_effects",
                    "storage_conditions",
                )
                for attr_key, tab_key in (
                    ("indications_source", "indications"),
                    ("contraindications_source", "before_use_warnings"),
                    ("usage_instructions_source", "usage_instructions"),
                    ("side_effects_source", "side_effects"),
                    ("storage_conditions_source", "storage_conditions"),
                    ("summary_source", "summary"),
                ):
                    tab_payload = detail_tabs.get(tab_key) or {}
                    if tab_payload.get("text"):
                        attributes[attr_key] = tab_payload["text"]
                for tab_key in description_tab_order:
                    tab_payload = detail_tabs.get(tab_key) or {}
                    tab_text = tab_payload.get("text")
                    if tab_text:
                        description_lines.append(f"{tab_payload.get('title') or tab_key}:\n{tab_text}")
            
            description = "\n\n".join(description_lines)
            
            # 4. Изображения
            images = []
            og_img = soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                images.append(urljoin(self.base_url, og_img["content"]))
                
            img_tags = soup.select(".swiper-slide img[src], img[src]")
            for img in img_tags:
                src = img.get("src")
                if not src:
                    continue
                src_lower = src.lower()
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

            external_id = self._extract_external_id_from_url(product_url)
            if not external_id:
                external_id = name

            # 5. Аналоги (Eşdeğeri / SGK Eşdeğeri)
            # На сайте ilacfiyati аналоги лежат на отдельных подстраницах /esdegeri и /sgk-esdegeri
            analogs = []
            sub_paths = [('/esdegeri', 'Eşdeğeri'), ('/sgk-esdegeri', 'SGK Eşdeğeri')]
            canonical_product_url = self._canonical_product_url(product_url)
            
            for path, source_tab in sub_paths:
                sub_url = canonical_product_url + path
                try:
                    # Добавляем небольшую паузу, чтобы не злить сервер
                    import time
                    time.sleep(1.5)
                    
                    sub_html = self._make_request(sub_url)
                    if sub_html:
                        sub_soup = BeautifulSoup(sub_html, 'html.parser')
                        # Ищем все ссылки на лекарства на этой странице
                        # Обычно они в таблицах или списках в центральной колонке
                        links = sub_soup.find_all('a', href=True)
                        for a in links:
                            analog = self._extract_analog_from_link(
                                a,
                                current_product_url=canonical_product_url,
                                source_tab=source_tab,
                            )
                            if analog:
                                analogs.append(analog)
                except Exception as e:
                    self.logger.error(f"Error fetching analogs from {sub_url}: {e}")
            
            # Удаляем дубликаты по URL
            seen_urls = set()
            unique_analogs = []
            for an in analogs:
                if an['url'] not in seen_urls:
                    seen_urls.add(an['url'])
                    unique_analogs.append(an)
            
            self.logger.info(f"Товар {name}: найдено аналогов {len(unique_analogs)}")

            return ScrapedProduct(
                name=name,
                description=description,
                price=price,
                currency="TRY",         
                url=product_url,
                images=images,
                external_id=external_id,
                brand=brand,            
                barcode=attributes.get('barcode', ''),
                is_available=True,      
                stock_quantity=3,       
                source=self.get_name(),
                attributes=attributes,
                analogs=unique_analogs
            )
            
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге детальной страницы {product_url}: {e}")
            return None
