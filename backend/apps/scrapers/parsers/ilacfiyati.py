"""Парсер для сайта ilacfiyati.com (лекарства и добавки)."""

import logging
import re
from typing import Dict, List, Optional, Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse
import httpx
from bs4 import BeautifulSoup
from celery.exceptions import SoftTimeLimitExceeded

from ..base.scraper import BaseScraper, ScrapedProduct, ScraperAccessBlockedError
from ..base.utils import clean_text, normalize_price

ILACFIYATI_PRICE_CURRENCIES = frozenset({"TRY", "USD", "EUR"})


class IlacFiyatiSourceError(RuntimeError):
    """Источник вернул пустую или неожиданную страницу вместо данных лекарства."""


class IlacFiyatiParser(BaseScraper):
    """Парсер для сайта ilacfiyati.com."""

    # Настоящая пагинация через ?pg= и поддержка start_page — авточепочка безопасна.
    SUPPORTS_PAGE_CHUNKING = True
    REPORTS_PAGES_PROCESSED = True
    REPORTS_NEXT_START_PAGE = True

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

    @classmethod
    def is_ilacfiyati_listing_url(cls, url: str) -> bool:
        parsed = urlparse(url or "")
        path_parts = [p for p in (parsed.path or url or "").strip("/").split("/") if p]
        return len(path_parts) == 1 and path_parts[0] in ("ilaclar", "takviye-edici-gida")

    @classmethod
    def supports_page_chunking_for_url(cls, url: str) -> bool:
        """Авточепочка по ?pg= безопасна только для листинга, не для карточки."""
        return cls.is_ilacfiyati_listing_url(url)

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

    @staticmethod
    def _extract_price_currency(value: str) -> str:
        """Return an explicit source currency, defaulting bare prices to TRY."""
        normalized = str(value or "").upper()
        if "€" in normalized or re.search(r"\bEUR\b", normalized):
            return "EUR"
        if "$" in normalized or re.search(r"\bUSD\b", normalized):
            return "USD"
        return "TRY"

    def _extract_labeled_price_text(self, soup: BeautifulSoup) -> str:
        """Read the medicine price from the source's current card layout."""
        label_value_selectors = (
            (".info-card__label", ".info-card__value"),
            (".price-card-label", ".price-card-value"),
        )
        for label_selector, value_selector in label_value_selectors:
            for label in soup.select(label_selector):
                label_text = self._normalize_tr_key(
                    clean_text(label.get_text(" ", strip=True))
                )
                if label_text != "ILAC FIYATI":
                    continue
                container = label.parent
                value = container.select_one(value_selector) if container else None
                if value is None:
                    continue
                # The visible value and tooltip currently match. Prefer the
                # tooltip when present because it is not visually truncated.
                return clean_text(value.get("title") or value.get_text(" ", strip=True))
        return ""

    def _canonical_product_url(self, product_url: str) -> str:
        parsed = urlparse(product_url)
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(parts) >= 3 and parts[0] in ("ilaclar", "takviye-edici-gida"):
            parts = parts[:2]
        path = "/" + "/".join(parts)
        return parsed._replace(path=path, params="", query="", fragment="").geturl().rstrip("/")

    @staticmethod
    def _listing_page_url(category_url: str, page: int) -> str:
        """Добавляет/заменяет pg, не ломая brand и другие фильтры URL."""
        parsed = urlparse(category_url)
        query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "pg"]
        if page > 1 or any(key == "pg" for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
            query.append(("pg", str(page)))
        return parsed._replace(query=urlencode(query, doseq=True), fragment="").geturl()

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
            except SoftTimeLimitExceeded:
                raise
            except ScraperAccessBlockedError:
                raise
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
        # Цену берём только из числа непосредственно перед TL/₺ — normalize_price
        # по всему тексту строки склеивала дозировку из названия с ценой
        # («ASIVIRAL 400 MG 25 TABLET … 125,45 TL» → 40025125.45)
        analog_price = None
        price_match = re.search(r"(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*(?:TL|₺)", context)
        if price_match:
            analog_price = normalize_price(price_match.group(1))
        analog = {
            "name": analog_name,
            "url": analog_url,
            "price": analog_price,
            "external_id": self._extract_external_id_from_url(analog_url),
            "source_tab": source_tab,
        }
        analog.update(self._extract_analog_codes(context))
        return analog

    def parse_product_list(self, category_url: str, max_pages: int = 10, start_page: int = 1):
        """
        Парсит список товаров из указанной категории.
        Поддерживает пагинацию через параметр `?pg=`.
        Генератор: отдаёт каждый товар сразу после парсинга.
        start_page — с какой страницы начинать (для авточепочки задач).
        max_pages — сколько страниц обработать в этом вызове (размер чанка).
        """
        self.has_more_pages = True
        self.pages_processed = 0
        self.next_start_page = start_page
        self.item_errors = 0
        self.stop_reason = ""
        count = 0
        page = start_page
        pages_parsed = 0
        previous_page_urls = None

        def extract_product_urls(html):
            soup = BeautifulSoup(html, 'html.parser')
            urls = []
            for link in soup.select('a[href*="/ilaclar/"], a[href*="/takviye-edici-gida/"]'):
                href = link.get('href')
                if not href or 'pg=' in href:
                    continue
                path_parts = urlparse(href).path.strip('/').split('/')
                if len(path_parts) >= 2 and path_parts[0] in ('ilaclar', 'takviye-edici-gida'):
                    full_url = urljoin(self.base_url, href)
                    if full_url not in urls:
                        urls.append(full_url)
            return urls

        if page > 1:
            previous_url = self._listing_page_url(category_url, page - 1)
            previous_html = self._make_request(previous_url)
            if previous_html:
                previous_page_urls = extract_product_urls(previous_html)

        try:
            self.logger.info(f"Начинаем парсинг товаров: {category_url} (страницы {start_page}+{max_pages})")

            while pages_parsed < max_pages:
                # Пока страница не завершена, безопасный курсор указывает на неё:
                # после soft-timeout уже сохранённые товары отсеет cache задачи.
                self.next_start_page = page
                url = self._listing_page_url(category_url, page)
                self.logger.info(f"Запрос страницы {page}: {url}")

                html = self._make_request(url)
                if not html:
                    raise IlacFiyatiSourceError(
                        f"IlacFiyati вернул пустую страницу каталога: {url}"
                    )

                product_urls = extract_product_urls(html)

                if not product_urls:
                    self.stop_reason = (
                        f"На странице {page} по заданным фильтрам товары не найдены; "
                        "каталог или выборка закончились."
                    )
                    self.logger.info(self.stop_reason)
                    self.has_more_pages = False
                    break

                if previous_page_urls and product_urls == previous_page_urls:
                    self.logger.info(
                        "IlacFiyati: страница %s повторяет предыдущую, каталог исчерпан.",
                        page,
                    )
                    self.stop_reason = (
                        f"Страница {page} повторяет предыдущую; каталог закончился."
                    )
                    self.has_more_pages = False
                    break

                for product_url in product_urls:
                    if self.max_products is not None and count >= self.max_products:
                        return

                    try:
                        detail = self.parse_product_detail(product_url)
                    except SoftTimeLimitExceeded:
                        raise
                    except ScraperAccessBlockedError:
                        raise
                    except IlacFiyatiSourceError as exc:
                        self.item_errors += 1
                        self.logger.error(
                            "IlacFiyati: карточка %s пропущена из-за ошибки источника: %s",
                            product_url,
                            exc,
                        )
                        continue
                    if detail and self.validate_product(detail):
                        count += 1
                        yield detail

                pages_parsed += 1
                self.pages_processed = pages_parsed
                previous_page_urls = product_urls
                page += 1
                self.next_start_page = page

        except SoftTimeLimitExceeded:
            raise
        except ScraperAccessBlockedError:
            raise
        except Exception:
            self.logger.exception("Ошибка при парсинге списка товаров IlacFiyati")
            raise

    def parse_market_snapshot(self, product_url: str) -> ScrapedProduct:
        """Получает только справочную цену и эквиваленты одной карточки.

        Пользовательская проверка не должна повторно скачивать все вкладки инструкции:
        это увеличивало бы один intent-запрос примерно с трёх страниц до двенадцати.
        Для БАДов эквиваленты лекарств неприменимы, поэтому их вкладки не запрашиваются.
        """

        canonical_url = self._canonical_product_url(product_url)
        is_medicine = urlparse(canonical_url).path.strip("/").startswith("ilaclar/")
        return self.parse_product_detail(
            canonical_url,
            include_detail_tabs=False,
            include_analogs=is_medicine,
            tolerate_analog_errors=True,
            preserve_transport_errors=True,
        )

    def parse_product_detail(
        self,
        product_url: str,
        *,
        include_detail_tabs: bool = True,
        include_analogs: bool = True,
        tolerate_analog_errors: bool = False,
        preserve_transport_errors: bool = False,
    ) -> ScrapedProduct:
        """
        Парсит детальную страницу товара.
        Извлекает название, цену и характеристики.
        """
        try:
            self.logger.info(f"Парсинг деталей товара: {product_url}")
            html = self._make_request(product_url)
            if not html:
                raise IlacFiyatiSourceError(
                    f"IlacFiyati вернул пустую карточку: {product_url}"
                )

            soup = BeautifulSoup(html, 'html.parser')
            
            # 1. Название товара
            name = ""
            # Selector priority matters: the current source page has a generic
            # marketing H1 before the medicine-specific H1.page-title.
            title_elem = None
            for selector in (
                '.product-name',
                'h1.page-title',
                'h2.page-title',
                '.font-size-22.text-primary.fw-bold',
                '.title',
                'h1',
                'h2',
            ):
                title_elem = soup.select_one(selector)
                if title_elem:
                    break
            if title_elem:
                for content in title_elem.contents:
                    if isinstance(content, str) and content.strip():
                        name = clean_text(content)
                        break
                if not name:
                    name = clean_text(title_elem.text)
            
            if not name:
                raise IlacFiyatiSourceError(
                    f"IlacFiyati: название препарата не найдено на странице {product_url}"
                )

            # 2. Цена
            price = None
            price_currency = "TRY"
            price_unpublished = False
            price_text = self._extract_labeled_price_text(soup)
            if price_text:
                parsed_price = normalize_price(price_text)
                if parsed_price is not None:
                    price_currency = self._extract_price_currency(price_text)
                if parsed_price == 0:
                    price_unpublished = True
                elif parsed_price is not None and parsed_price > 0:
                    price = parsed_price

            if price is None and not price_unpublished:
                for row in soup.find_all('tr'):
                    cols = row.find_all(['th', 'td'])
                    if len(cols) == 2:
                        key_raw = self._normalize_tr_key(clean_text(cols[0].text))
                        if 'FIYAT' in key_raw and 'KAMU' not in key_raw:
                            price_text = clean_text(cols[1].text)
                            parsed_price = normalize_price(price_text)
                            if parsed_price is not None:
                                price_currency = self._extract_price_currency(price_text)
                            if parsed_price == 0:
                                # IlacFiyati uses 0,00 when a current public price has
                                # not been published. Preserve that distinction for
                                # on-demand checks without projecting zero into the
                                # product catalogue as a real price.
                                price_unpublished = True
                                break
                            if parsed_price is not None and parsed_price > 0:
                                price = parsed_price
                                break
            if price is None and not price_unpublished:
                currency_markers = ('\u20BA', ' TL', ' TRY', '\u20AC', ' EUR', '$', ' USD')
                price_tags = soup.find_all(
                    string=lambda x: x
                    and any(marker in str(x).upper() for marker in currency_markers)
                )
                for text_node in price_tags:
                    text_clean = text_node.strip()
                    if any(char.isdigit() for char in text_clean):
                        parsed_price = normalize_price(text_clean)
                        if parsed_price is not None and parsed_price > 0:
                            price = parsed_price
                            price_currency = self._extract_price_currency(text_clean)
                            break
            

            # 3. Дополнительные атрибуты (таблицы, характеристики)
            attributes = {}
            description_lines = []
            
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
                            if not attributes.get('manufacturer'):
                                attributes['manufacturer'] = val
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
            detail_tabs = self._fetch_detail_tabs(product_url) if include_detail_tabs else {}
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
            analog_fetch_errors = 0
            sub_paths = (
                [('/esdegeri', 'Eşdeğeri'), ('/sgk-esdegeri', 'SGK Eşdeğeri')]
                if include_analogs
                else []
            )
            canonical_product_url = self._canonical_product_url(product_url)
            
            for path, source_tab in sub_paths:
                sub_url = canonical_product_url + path
                try:
                    # Добавляем небольшую паузу, чтобы не злить сервер
                    import time
                    time.sleep(1.5)
                    
                    sub_html = self._make_request(sub_url)
                    if not sub_html:
                        raise IlacFiyatiSourceError(
                            f"IlacFiyati вернул пустую вкладку аналогов: {sub_url}"
                        )
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
                except SoftTimeLimitExceeded:
                    raise
                except ScraperAccessBlockedError:
                    if not tolerate_analog_errors:
                        raise
                    analog_fetch_errors += 1
                    self.logger.warning(
                        "IlacFiyati blocked an optional analog tab: %s", sub_url
                    )
                except Exception as e:
                    analog_fetch_errors += 1
                    self.logger.error(f"Error fetching analogs from {sub_url}: {e}")
            
            # Один препарат может присутствовать в обеих вкладках. Объединяем
            # строки по URL, сохраняя коды и происхождение из обеих вкладок.
            analogs_by_url = {}
            for analog in analogs:
                analog_url = analog["url"]
                existing = analogs_by_url.get(analog_url)
                if existing is None:
                    analogs_by_url[analog_url] = dict(analog)
                    continue
                for field_name in (
                    "barcode",
                    "atc_code",
                    "sgk_equivalent_code",
                    "price",
                ):
                    if not existing.get(field_name) and analog.get(field_name):
                        existing[field_name] = analog[field_name]
                source_tabs = [
                    value.strip()
                    for value in str(existing.get("source_tab") or "").split(",")
                    if value.strip()
                ]
                next_source_tab = str(analog.get("source_tab") or "").strip()
                if next_source_tab and next_source_tab not in source_tabs:
                    source_tabs.append(next_source_tab)
                existing["source_tab"] = ", ".join(source_tabs)
            unique_analogs = list(analogs_by_url.values())
            
            self.logger.info(f"Товар {name}: найдено аналогов {len(unique_analogs)}")

            product = ScrapedProduct(
                name=name,
                description=description,
                price=price,
                currency=price_currency,
                url=product_url,
                images=images,
                external_id=external_id,
                barcode=attributes.get('barcode', ''),
                # IlacFiyati is an informational price catalogue and explicitly does
                # not sell products. "AKTIF" on the page is a catalogue/registration
                # state, not supplier stock, so availability must stay fail-closed.
                is_available=False,
                stock_quantity=None,
                source=self.get_name(),
                attributes=attributes,
                analogs=unique_analogs
            )
            # Диагностика нужна интеграционному сервису для счётчиков запуска,
            # но не должна попадать в атрибуты/БД самого препарата.
            product.analog_fetch_errors = analog_fetch_errors
            product.price_unpublished = price_unpublished
            return product

        except SoftTimeLimitExceeded:
            raise
        except ScraperAccessBlockedError:
            raise
        except httpx.HTTPError as exc:
            if preserve_transport_errors:
                raise
            raise IlacFiyatiSourceError(
                f"Не удалось получить карточку IlacFiyati {product_url}"
            ) from exc
        except IlacFiyatiSourceError:
            raise
        except Exception as e:
            self.logger.exception("Ошибка при парсинге детальной страницы %s", product_url)
            raise IlacFiyatiSourceError(
                f"Не удалось разобрать карточку IlacFiyati {product_url}: {e}"
            ) from e
