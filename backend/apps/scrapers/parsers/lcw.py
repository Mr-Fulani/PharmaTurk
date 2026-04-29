"""Парсер для lcw.com (LC Waikiki)."""

import copy
import re
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote_plus, urljoin, urlparse

from bs4 import BeautifulSoup

from ..base.scraper import BaseScraper, ScrapedProduct
from ..base.utils import clean_text, extract_currency, normalize_price


class LcwParser(BaseScraper):
    """Парсер для lcw.com."""

    DEFAULT_ASSUMED_STOCK_QUANTITY = 1000
    MAX_VARIANTS_PER_PRODUCT = 24
    PRODUCT_PATH_RE = re.compile(r"-o-(\d+)(?:$|[/?#])")
    CATEGORY_PATH_RE = re.compile(r"-t-(\d+)(?:$|[/?#])")
    PRICE_RE = re.compile(r"(\d[\d.]*,\d{2}\s*(?:TL|₺))", re.IGNORECASE)
    VARIANT_COUNT_RE = re.compile(r"\s+\+\d+\s*$")
    SIZE_SPLIT_RE = re.compile(r"\s{2,}|\n+")
    SKIP_IMAGE_HINTS = (
        "logo",
        "icon",
        "sprite",
        "placeholder",
        "banner",
        "payment",
        "social",
    )

    def __init__(self, base_url: str = "https://www.lcw.com", **kwargs):
        super().__init__(base_url=base_url, delay_range=(1.5, 3.5), **kwargs)

    def get_name(self) -> str:
        return "lcw"

    def get_supported_domains(self) -> List[str]:
        return ["lcw.com", "www.lcw.com"]

    def parse_categories(self) -> List[Dict[str, Any]]:
        html = self._make_request(self.base_url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        categories: List[Dict[str, Any]] = []
        seen_urls = set()

        for anchor in soup.select("a[href]"):
            href = anchor.get("href", "").strip()
            if not self._is_category_url(href):
                continue

            absolute_url = urljoin(self.base_url, href)
            if absolute_url in seen_urls:
                continue

            name = clean_text(anchor.get_text(" ", strip=True))
            if not name or len(name) < 2:
                continue

            seen_urls.add(absolute_url)
            categories.append(
                {
                    "name": name,
                    "url": absolute_url,
                    "external_id": self._extract_category_id(absolute_url),
                    "source": self.get_name(),
                }
            )

        return categories

    def parse_product_list(self, category_url: str, max_pages: int = 10) -> List[ScrapedProduct]:
        html = self._make_request(category_url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        products: List[ScrapedProduct] = []
        seen_urls = set()
        seen_family_urls = set()
        seen_group_ids = set()
        seen_family_keys = set()

        for anchor in soup.select("a[href]"):
            href = anchor.get("href", "").strip()
            if not self._is_product_url(href):
                continue

            product_url = urljoin(self.base_url, href)
            if product_url in seen_urls or product_url in seen_family_urls:
                continue

            seen_urls.add(product_url)
            detail_html = self._make_request(product_url)
            parsed_variant = self._parse_single_variant(product_url, detail_html) if detail_html else None
            family_key = self._build_family_key(parsed_variant)
            if family_key and family_key in seen_family_keys:
                continue

            product = None
            if parsed_variant:
                product = self._parse_product_group(
                    product_url,
                    visited_urls=set(),
                    initial_variant=parsed_variant,
                )
            else:
                product = self.parse_product_detail(product_url)
            if not product:
                product = self._build_list_product(anchor, product_url, category_url)

            group_id = ""
            if product and isinstance(product.attributes, dict):
                group_id = str(product.attributes.get("variant_group_id") or "").strip()
            if group_id and group_id in seen_group_ids:
                continue
            if group_id:
                seen_group_ids.add(group_id)
            if family_key:
                seen_family_keys.add(family_key)

            if product and isinstance(product.attributes, dict):
                for variant in product.attributes.get("fashion_variants", []) or []:
                    variant_url = str(variant.get("external_url") or "").strip()
                    if variant_url:
                        seen_family_urls.add(variant_url)

            if product and self.validate_product(product):
                products.append(product)

            if self.max_products and len(products) >= self.max_products:
                break

        return products

    def parse_product_detail(self, product_url: str) -> Optional[ScrapedProduct]:
        return self._parse_product_group(product_url, visited_urls=set())

    def _parse_product_group(
        self,
        product_url: str,
        *,
        visited_urls: Set[str],
        initial_variant: Optional[Dict[str, Any]] = None,
    ) -> Optional[ScrapedProduct]:
        current_variant = initial_variant
        if not current_variant:
            html = self._make_request(product_url)
            if not html:
                return None
            current_variant = self._parse_single_variant(product_url, html)
        if not current_variant:
            return None

        visited_urls.add(product_url)
        variant_urls = self._extract_color_variant_urls(
            current_variant["soup"],
            current_url=product_url,
        )
        if len(variant_urls) > self.MAX_VARIANTS_PER_PRODUCT:
            self.logger.warning(
                "LCW: too many variant URLs for %s (%d), truncating to %d",
                product_url,
                len(variant_urls),
                self.MAX_VARIANTS_PER_PRODUCT,
            )
            variant_urls = variant_urls[: self.MAX_VARIANTS_PER_PRODUCT]
        group_urls = [product_url] + [url for url in variant_urls if url not in visited_urls]

        self.logger.info(
            "LCW: building product group for %s with %d variant URLs",
            product_url,
            len(group_urls),
        )

        variants = [self._variant_payload_from_parsed(current_variant, sort_order=0)]
        for sort_order, variant_url in enumerate(group_urls[1:], start=1):
            self.logger.info(
                "LCW: fetching variant %d/%d for %s",
                sort_order + 1,
                len(group_urls),
                product_url,
            )
            variant_html = self._make_request(variant_url)
            if not variant_html:
                continue
            parsed_variant = self._parse_single_variant(variant_url, variant_html)
            if not parsed_variant:
                continue
            visited_urls.add(variant_url)
            variants.append(self._variant_payload_from_parsed(parsed_variant, sort_order=sort_order))

        variant_ids = [self._extract_product_id(url) for url in group_urls if self._extract_product_id(url)]
        group_external_id = self._build_group_external_id(variant_ids, current_variant)

        attributes = copy.deepcopy(current_variant["attributes"])
        attributes["fashion_variants"] = variants
        attributes["variant_group_id"] = group_external_id
        attributes["group_sku"] = current_variant.get("group_sku") or current_variant.get("sku") or ""
        if current_variant.get("color"):
            attributes["color"] = current_variant["color"]

        return ScrapedProduct(
            name=current_variant["name"],
            description=current_variant["description"],
            price=float(current_variant["price"]) if current_variant["price"] is not None else None,
            currency=current_variant["currency"],
            url=product_url,
            images=current_variant["images"],
            category=current_variant["category"] or "",
            brand=current_variant["brand"] or "",
            external_id=group_external_id,
            sku=current_variant.get("group_sku") or current_variant.get("sku") or "",
            is_available=any(v.get("is_available", True) for v in variants),
            stock_quantity=sum(
                int(v.get("stock_quantity") or 0) for v in variants if v.get("stock_quantity") is not None
            ) or None,
            attributes=attributes,
            source=self.get_name(),
        )

    def search_products(self, query: str, max_results: int = 50) -> List[ScrapedProduct]:
        search_url = f"{self.base_url}/arama?q={quote_plus(query)}"
        self.max_products = max_results
        return self.parse_product_list(search_url, max_pages=1)

    @classmethod
    def is_lcw_product_url(cls, url: str) -> bool:
        path = urlparse(url).path or url
        return bool(cls.PRODUCT_PATH_RE.search(path))

    @classmethod
    def is_lcw_category_url(cls, url: str) -> bool:
        path = urlparse(url).path or url
        return bool(cls.CATEGORY_PATH_RE.search(path))

    def _is_product_url(self, url: str) -> bool:
        return self.is_lcw_product_url(url) and "/magaza/" not in url

    def _is_category_url(self, url: str) -> bool:
        return self.is_lcw_category_url(url) and "/magaza/" not in url

    def _build_list_product(
        self,
        anchor,
        product_url: str,
        category_url: str,
    ) -> Optional[ScrapedProduct]:
        anchor_text = clean_text(anchor.get_text(" ", strip=True))
        if not anchor_text:
            return None

        price_text = self._extract_price_text(anchor_text)
        name = anchor_text
        if price_text:
            name = clean_text(name.replace(price_text, ""))
        name = self.VARIANT_COUNT_RE.sub("", name).strip()

        if not name:
            return None

        return ScrapedProduct(
            name=name,
            price=float(normalize_price(price_text)) if price_text else None,
            currency=extract_currency(price_text) if price_text else "TRY",
            url=product_url,
            images=[],
            category=self._extract_category_name_from_url(category_url),
            brand="",
            external_id=f"lcw-{self._extract_product_id(product_url)}",
            source=self.get_name(),
        )

    def _parse_single_variant(self, product_url: str, html: str) -> Optional[Dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        page_text = soup.get_text("\n", strip=True)

        name = self._extract_name(soup)
        if not name:
            return None

        price_text = self._extract_price_text(page_text)
        price = normalize_price(price_text)
        sku = self._extract_sku(page_text)
        brand = self._extract_attribute_value(page_text, "Marka")
        category = self._extract_heading_category(soup) or self._extract_attribute_value(page_text, "Ürün Tipi")
        description = self._extract_description_from_soup(soup) or self._extract_description(page_text)
        images = self._extract_images(soup, name)
        attributes = self._extract_attributes(page_text)
        og_image_url = self._extract_og_image_url(soup)
        color = self._extract_color(page_text)
        sizes = self._extract_sizes(soup, page_text)
        is_available = "tukendi" not in page_text.lower() and "tükendi" not in page_text.lower()
        group_sku = self._extract_group_sku(page_text, sku)
        if og_image_url:
            attributes["og_image_url"] = og_image_url

        return {
            "url": product_url,
            "soup": soup,
            "page_text": page_text,
            "name": name,
            "price": price,
            "currency": extract_currency(price_text) if price_text else "TRY",
            "sku": sku or "",
            "group_sku": group_sku or "",
            "brand": brand or "",
            "category": category or "",
            "description": description,
            "images": images,
            "attributes": attributes,
            "color": color,
            "sizes": sizes,
            "is_available": is_available,
            "product_id": self._extract_product_id(product_url),
        }

    def _variant_payload_from_parsed(self, parsed: Dict[str, Any], *, sort_order: int) -> Dict[str, Any]:
        return {
            "external_id": f"lcw-var-{parsed['product_id']}",
            "sort_order": sort_order,
            "color": parsed.get("color", ""),
            "display_name": parsed.get("name", ""),
            "price": float(parsed["price"]) if parsed.get("price") is not None else None,
            "currency": parsed.get("currency") or "TRY",
            "external_url": parsed.get("url") or "",
            "images": list(parsed.get("images") or []),
            "stock_quantity": (
                self.DEFAULT_ASSUMED_STOCK_QUANTITY if parsed.get("is_available", True) else 0
            ),
            "is_available": bool(parsed.get("is_available", True)),
            "sizes": list(parsed.get("sizes") or []),
            "sku": parsed.get("sku") or "",
        }

    def _extract_name(self, soup: BeautifulSoup) -> str:
        meta_title = soup.find("meta", property="og:title")
        if meta_title and meta_title.get("content"):
            title = clean_text(meta_title["content"])
            return re.sub(r"\s*\|\s*LCW\s*$", "", title).strip()

        title_tag = soup.find("title")
        if title_tag:
            title = clean_text(title_tag.get_text(" ", strip=True))
            title = re.sub(r"\s*\|\s*LCW\s*$", "", title).strip()
            if title:
                return title

        heading = soup.find(["h1", "h2"])
        return clean_text(heading.get_text(" ", strip=True)) if heading else ""

    def _extract_description(self, page_text: str) -> str:
        return self._build_rich_description(page_text)

    def _extract_description_from_soup(self, soup: BeautifulSoup) -> str:
        rich_from_text = self._build_rich_description(soup.get_text("\n", strip=True))
        if rich_from_text and not any(
            marker in rich_from_text
            for marker in ("Ürün İçeriği ve Özellikleri", "Bakım Bilgileri", "Kumaş Rehberi")
        ):
            return rich_from_text

        stop_markers = (
            "Ürün İçeriği ve Özellikleri",
            "Kargo ve İade",
            "Bakım Bilgileri",
            "İmalatçı / İthalatçı",
            "Destek",
            "Manken Bilgisi",
        )
        skip_exact = {
            "Kampanyalar",
            "Ürün Açıklaması",
        }
        heading = soup.find(
            string=lambda value: (
                isinstance(value, str)
                and "Ürün Açıklaması" in value
                and getattr(getattr(value, "parent", None), "name", None) not in {"script", "style"}
            )
        )
        if not heading:
            return ""

        texts: List[str] = []
        seen = set()
        anchor = getattr(heading, "parent", None)
        if anchor is None:
            return ""

        for node in anchor.next_elements:
            if node is heading:
                continue
            raw_text = ""
            if isinstance(node, str):
                raw_text = clean_text(node)
            elif getattr(node, "name", None) in {"div", "p", "span", "li"}:
                raw_text = clean_text(node.get_text(" ", strip=True))

            if not raw_text:
                continue
            if raw_text in stop_markers or any(raw_text.startswith(marker) for marker in stop_markers):
                break
            if raw_text in skip_exact:
                continue
            if raw_text not in seen:
                texts.append(raw_text)
                seen.add(raw_text)

        description = clean_text(" ".join(texts))
        description = re.sub(r"^(?:Kargo ve İade\s*)+", "", description, flags=re.IGNORECASE).strip()
        description = re.sub(r"^(?:Ürün Açıklaması\s*:?\s*)+", "", description, flags=re.IGNORECASE).strip()
        description = re.sub(r"^(?:Kampanyalar\s*)+", "", description, flags=re.IGNORECASE).strip()
        description = re.sub(r"^:\s*", "", description).strip()
        description = re.sub(r"^[A-Z0-9-]+\s*-\s*", "", description).strip()
        return description

    def _build_rich_description(self, page_text: str) -> str:
        raw_text = page_text or ""
        text = clean_text(raw_text)
        if not text or "Ürün Açıklaması" not in text:
            return ""

        sections: List[str] = []

        intro_match = re.search(
            r"Ürün Açıklaması\s*:?\s*([A-Z0-9-]+\s*-\s*[^ ]+)\s+(.+?)(?:Ürün İçeriği ve Özellikleri|Kargo ve İade|$)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if intro_match:
            product_code = clean_text(intro_match.group(1))
            intro_text = clean_text(intro_match.group(2))
            if product_code:
                sections.append(f"Ürün Kodu: {product_code}")
            if intro_text:
                sections.append(intro_text)
        else:
            fallback_intro = re.search(
                r"Ürün Açıklaması\s*(.+?)(?:Ürün İçeriği ve Özellikleri|Kargo ve İade|$)",
                raw_text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if fallback_intro:
                intro_text = clean_text(fallback_intro.group(1))
                intro_text = re.sub(r"^(?:Kampanyalar\s*)+", "", intro_text, flags=re.IGNORECASE).strip()
                intro_text = re.sub(
                    r"^:\s*[A-Z0-9-]+\s*-\s*",
                    "",
                    intro_text,
                ).strip()
                intro_text = re.split(
                    r"\b(?:Manken Bilgisi|Ürün İçeriği ve Özellikleri|Kargo ve İade)\b",
                    intro_text,
                    maxsplit=1,
                    flags=re.IGNORECASE,
                )[0].strip()
                if intro_text:
                    sections.append(intro_text)

        attrs_block_match = re.search(
            r"Ürün İçeriği ve Özellikleri\s*(.+?)(?:Kumaş Rehberi|Bakım Bilgileri|Destek|$)",
            raw_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        attrs_lines: List[str] = []
        if attrs_block_match:
            attrs_block_raw = attrs_block_match.group(1)
            next_labels_pattern = (
                r"(?:Ana Kumaş|Menşei|Satıcı|Marka|Ürün Tipi|Cinsiyet|Kumaş|Desen|Malzeme|"
                r"İmalatçı / İthalatçı / Yetkili Temsilci / İfa Hizmet Sağlayıcı)\s*:"
            )
            direct_labels = [
                "Ana Kumaş",
                "Ürün Tipi",
                "Kumaş",
                "Desen",
                "Malzeme",
            ]
            for label in direct_labels:
                match = re.search(
                    rf"(?mi)^\s*{re.escape(label)}\s*:\s*(.+?)(?=^\s*{next_labels_pattern}|\Z)",
                    attrs_block_raw,
                    flags=re.DOTALL,
                )
                if not match:
                    continue
                value = clean_text(match.group(1))
                if value:
                    attrs_lines.append(f"{label}: {value}")

            manufacturer_match = re.search(
                rf"(?mi)^\s*İmalatçı / İthalatçı / Yetkili Temsilci / İfa Hizmet Sağlayıcı\s*:\s*(.+?)(?=^\s*{next_labels_pattern}|\Z)",
                attrs_block_raw,
                flags=re.DOTALL,
            )
            if manufacturer_match:
                manufacturer_value = clean_text(manufacturer_match.group(1))
                if manufacturer_value:
                    manufacturer_value = manufacturer_value.split(" 15 Temmuz Mah.")[0].split(" info@")[0].strip()
                    attrs_lines = (
                        attrs_lines[:1]
                        + [
                            "İmalatçı / İthalatçı / Yetkili Temsilci / İfa Hizmet Sağlayıcı:",
                            manufacturer_value,
                            "Daha çok bilgi",
                        ]
                        + attrs_lines[1:]
                    )

        if attrs_lines:
            sections.append("Ürün İçeriği ve Özellikleri")
            sections.append("\n".join(attrs_lines))

        if "Kumaş Rehberi" in text:
            sections.append("Kumaş Rehberi")

        care_lines: List[str] = []
        if "Bakım Bilgileri" in text:
            care_lines.append("Bakım Bilgileri")
        if "Giysilerinizi Nasıl Yıkamalısınız?" in text:
            care_lines.append("Giysilerinizi Nasıl Yıkamalısınız?")
        care_match = re.search(
            r"Bakım Bilgileri\s*:?\s*(.+?)(?:Destek|Sipariş Takip|Whatsapp Destek|Yardım|$)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if care_match:
            care_block = clean_text(care_match.group(1))
            care_labels = [
                "KURU TEMİZLEME YAPILAMAZ",
                "ÜTÜLEMEYİNİZ",
                "TAMBURLU KURUTMA YAPMAYINIZ",
                "AĞARTICI KULLANMAYINIZ",
                "YIKAMAYINIZ",
            ]
            title_map = {
                "KURU TEMİZLEME YAPILAMAZ": "Kuru Temizleme Yapılamaz",
                "ÜTÜLEMEYİNİZ": "Ütülemeyiniz",
                "TAMBURLU KURUTMA YAPMAYINIZ": "Tamburlu Kurutma Yapmayınız",
                "AĞARTICI KULLANMAYINIZ": "Ağartıcı Kullanmayınız",
                "YIKAMAYINIZ": "Yıkamayınız",
            }
            for label in care_labels:
                if label in care_block:
                    care_lines.append(label)
                    care_lines.append(title_map[label])
        if care_lines:
            sections.append("\n".join(care_lines))

        return "\n\n".join(section for section in sections if section).strip()

    def _extract_og_image_url(self, soup: BeautifulSoup) -> str:
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            return urljoin(self.base_url, og_image["content"])
        return ""

    def _extract_heading_category(self, soup: BeautifulSoup) -> str:
        headings = soup.find_all(["h1", "h2"])
        if len(headings) >= 2:
            return clean_text(headings[1].get_text(" ", strip=True))
        return ""

    def _extract_attributes(self, page_text: str) -> Dict[str, Any]:
        attributes: Dict[str, Any] = {}
        match = re.search(
            r"Ürün İçeriği ve Özellikleri\s*(.+?)(?:İmalatçı / İthalatçı|Bakım Bilgileri|Destek|$)",
            page_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return attributes

        block = match.group(1)
        for line in [clean_text(part) for part in block.splitlines()]:
            if ":" not in line:
                continue
            key, value = [clean_text(part) for part in line.split(":", 1)]
            if not key or not value:
                continue
            if key.lower() in {"marka", "satıcı"}:
                continue
            attributes[key.lower().replace(" ", "_")] = value

        return attributes

    def _extract_attribute_value(self, page_text: str, label: str) -> str:
        match = re.search(
            rf"{re.escape(label)}\s*:\s*(.+)",
            page_text,
            flags=re.IGNORECASE,
        )
        return clean_text(match.group(1)) if match else ""

    def _extract_images(self, soup: BeautifulSoup, product_name: str) -> List[str]:
        images_by_key: Dict[str, str] = {}
        scores_by_key: Dict[str, int] = {}
        og_image_url = ""
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            og_image_url = urljoin(self.base_url, og_image["content"])

        for img in soup.select("img[src], img[data-src], img[data-zoom], img[data-image], img[data-original]"):
            source = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-zoom")
                or img.get("data-image")
                or img.get("data-original")
            )
            if not source:
                continue

            full_url = urljoin(self.base_url, source)
            alt_text = clean_text(img.get("alt", ""))
            if (
                alt_text
                and product_name.lower() not in alt_text.lower()
                and len(alt_text.split()) <= 4
                and not self._is_lcw_product_gallery_image_url(full_url)
            ):
                continue
            self._store_image_candidate(full_url, images_by_key, scores_by_key)

        # У LCW часть галереи может приезжать как прямые ссылки <a href="...jpg">,
        # особенно на карточках без полноценного набора <img> для всех слайдов.
        for anchor in soup.select("a[href]"):
            href = anchor.get("href", "").strip()
            if not href:
                continue
            full_url = urljoin(self.base_url, href)
            if not self._looks_like_image_url(full_url):
                continue
            self._store_image_candidate(full_url, images_by_key, scores_by_key)

        # OG-изображение используем только как fallback для SEO/карточек,
        # если реальная галерея на странице не нашлась.
        if not images_by_key and og_image_url:
            image_key = self._canonicalize_image_url(og_image_url)
            images_by_key[image_key] = og_image_url
            scores_by_key[image_key] = self._image_resolution_score(og_image_url)

        return list(images_by_key.values())

    def _store_image_candidate(
        self,
        image_url: str,
        images_by_key: Dict[str, str],
        scores_by_key: Dict[str, int],
    ) -> None:
        source_lower = image_url.lower()
        if source_lower.endswith(".svg"):
            return
        if any(hint in source_lower for hint in self.SKIP_IMAGE_HINTS):
            return

        image_key = self._canonicalize_image_url(image_url)
        score = self._image_resolution_score(image_url)
        if image_key not in images_by_key or score > scores_by_key.get(image_key, -1):
            images_by_key[image_key] = image_url
            scores_by_key[image_key] = score

    def _looks_like_image_url(self, url: str) -> bool:
        lowered = url.lower()
        if lowered.endswith((".jpg", ".jpeg", ".png", ".webp")):
            return True
        return self._is_lcw_product_gallery_image_url(lowered)

    def _is_lcw_product_gallery_image_url(self, url: str) -> bool:
        lowered = url.lower()
        return "img-lcwaikiki.mncdn.com" in lowered and "/productimages/" in lowered

    def _canonicalize_image_url(self, image_url: str) -> str:
        canonical = re.sub(r"/mnpadding/\d+/\d+/ffffff/", "/", image_url)
        canonical = re.sub(r"/mnpadding/\d+/\d+/", "/", canonical)
        return canonical

    def _image_resolution_score(self, image_url: str) -> int:
        match = re.search(r"/mnpadding/(\d+)/(\d+)/", image_url)
        if not match:
            return 0
        return int(match.group(1)) * int(match.group(2))

    def _extract_color(self, page_text: str) -> str:
        match = re.search(r"Renk\s*:\s*(.+?)(?:Renk seçenekleri|Beden:|Sepete Ekle|$)", page_text, re.IGNORECASE | re.DOTALL)
        return clean_text(match.group(1)) if match else ""

    def _extract_sizes(self, soup: BeautifulSoup, page_text: str) -> List[Dict[str, Any]]:
        soup_sizes = self._extract_sizes_from_soup(soup)
        if soup_sizes:
            return soup_sizes

        return self._extract_sizes_from_text(page_text)

    def _extract_sizes_from_soup(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        heading = soup.find(
            string=lambda value: (
                isinstance(value, str)
                and "Beden" in value
                and getattr(getattr(value, "parent", None), "name", None) not in {"script", "style"}
            )
        )
        if not heading:
            return []

        stop_markers = ("Bedenini Keşfet", "Sepete Ekle", "Ürün Açıklaması", "Renk seçenekleri")
        sizes: List[Dict[str, Any]] = []
        seen = set()

        def add_candidate(text_value: str, available: bool) -> None:
            candidate = clean_text(text_value)
            if not candidate or len(candidate) > 20:
                return
            lowered = candidate.lower()
            if any(token in lowered for token in ("beden", "keşfet", "sepete", "ekle", "urun", "ürün")):
                return
            if candidate in seen:
                return
            seen.add(candidate)
            sizes.append(
                {
                    "size": candidate,
                    "is_available": available,
                    "stock_quantity": self.DEFAULT_ASSUMED_STOCK_QUANTITY if available else 0,
                    "sort_order": len(sizes),
                }
            )

        container = getattr(heading, "parent", None)
        if container is None:
            return []

        for node in container.next_elements:
            if node is heading:
                continue
            if isinstance(node, str):
                raw_text = clean_text(node)
                if not raw_text:
                    continue
                if any(raw_text.startswith(marker) for marker in stop_markers):
                    break
                continue

            tag_name = getattr(node, "name", None)
            if tag_name not in {"button", "span", "label", "div", "li", "a"}:
                continue

            node_text = clean_text(node.get_text(" ", strip=True))
            if not node_text:
                continue
            if any(node_text.startswith(marker) for marker in stop_markers):
                break

            if tag_name == "div" and len(node_text.split()) > 4:
                continue

            classes = " ".join(node.get("class", [])).lower()
            available = not (
                node.has_attr("disabled")
                or str(node.get("aria-disabled", "")).lower() == "true"
                or any(
                    hint in classes
                    for hint in ("disabled", "passive", "inactive", "out-of-stock", "outofstock", "sold-out")
                )
            )
            add_candidate(node_text, available)

        return sizes

    def _extract_sizes_from_text(self, page_text: str) -> List[Dict[str, Any]]:
        match = re.search(r"Beden:\s*(.+?)(?:Bedenini Keşfet|Sepete Ekle|Ürün Açıklaması|$)", page_text, re.IGNORECASE | re.DOTALL)
        if not match:
            return []

        raw_block = match.group(1)
        candidates = [clean_text(part) for part in self.SIZE_SPLIT_RE.split(raw_block) if clean_text(part)]
        sizes: List[Dict[str, Any]] = []
        seen = set()
        for idx, candidate in enumerate(candidates):
            if len(candidate) > 20:
                continue
            lowered = candidate.lower()
            if any(token in lowered for token in ("beden", "keşfet", "sepete", "ekle")):
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            sizes.append(
                {
                    "size": candidate,
                    "is_available": True,
                    "stock_quantity": self.DEFAULT_ASSUMED_STOCK_QUANTITY,
                    "sort_order": idx,
                }
            )
        return sizes

    def _extract_group_sku(self, page_text: str, sku: str) -> str:
        if sku and "-" in sku:
            return sku.split("-", 1)[0].strip()

        match = re.search(r":\s*([A-Z0-9.-]{5,})\s*-\s*[A-ZÇĞİÖŞÜa-zçğıöşü ]+\s*-", page_text)
        if match:
            return clean_text(match.group(1))
        return sku or ""

    def _extract_color_variant_urls(self, soup: BeautifulSoup, *, current_url: str) -> List[str]:
        current_id = self._extract_product_id(current_url)
        candidates: List[str] = []
        seen = set()
        anchors = self._find_color_option_anchors(soup)
        for href in self._iter_variant_hrefs_from_anchors(anchors):
            full_url = urljoin(self.base_url, href)
            if full_url == current_url:
                continue
            product_id = self._extract_product_id(full_url)
            if not product_id or product_id == current_id:
                continue
            if full_url not in seen:
                candidates.append(full_url)
                seen.add(full_url)

        for href in self._extract_variant_hrefs_from_embedded_data(soup):
            full_url = urljoin(self.base_url, href)
            if full_url == current_url:
                continue
            product_id = self._extract_product_id(full_url)
            if not product_id or product_id == current_id:
                continue
            if full_url not in seen:
                candidates.append(full_url)
                seen.add(full_url)
        return candidates

    def _iter_variant_hrefs_from_anchors(self, anchors: List[Any]) -> List[str]:
        hrefs: List[str] = []
        for anchor in anchors:
            href = anchor.get("href", "").strip()
            if self._is_product_url(href):
                hrefs.append(href)
        return hrefs

    def _find_color_option_anchors(self, soup: BeautifulSoup) -> List[Any]:
        color_heading = soup.find(
            string=lambda value: (
                isinstance(value, str)
                and "Renk seçenekleri" in value
                and getattr(getattr(value, "parent", None), "name", None) not in {"script", "style"}
            )
        )
        if not color_heading:
            return self._find_fallback_product_anchors(soup)

        anchors: List[Any] = []
        seen_ids = set()

        def extend_from_node(node) -> None:
            if node is None or not hasattr(node, "select"):
                return
            for anchor in node.select("a[href]"):
                anchor_id = id(anchor)
                if anchor_id in seen_ids:
                    continue
                if anchor.find("img") or not clean_text(anchor.get_text(" ", strip=True)):
                    anchors.append(anchor)
                    seen_ids.add(anchor_id)

        block = None
        parent = getattr(color_heading, "parent", None)
        while parent is not None:
            links = parent.select("a[href]") if hasattr(parent, "select") else []
            if len(links) >= 2:
                block = parent
                break
            parent = getattr(parent, "parent", None)

        if block is None:
            block = getattr(color_heading, "parent", None)

        if block is not None:
            extend_from_node(block)

        sibling = getattr(color_heading, "next_sibling", None)
        while sibling is not None:
            sibling_text = clean_text(getattr(sibling, "get_text", lambda *args, **kwargs: "")(" ", strip=True))
            if sibling_text.startswith("Beden"):
                break
            extend_from_node(sibling)
            sibling = getattr(sibling, "next_sibling", None)

        sibling = getattr(getattr(color_heading, "parent", None), "next_sibling", None)
        while sibling is not None:
            sibling_text = clean_text(getattr(sibling, "get_text", lambda *args, **kwargs: "")(" ", strip=True))
            if sibling_text.startswith("Beden"):
                break
            extend_from_node(sibling)
            sibling = getattr(sibling, "next_sibling", None)

        if anchors:
            return anchors

        return self._find_fallback_product_anchors(soup)

    def _extract_variant_hrefs_from_embedded_data(self, soup: BeautifulSoup) -> List[str]:
        hrefs: List[str] = []
        seen = set()

        script_texts = [
            script.string or script.get_text(" ", strip=False)
            for script in soup.find_all("script")
        ]
        url_pattern = re.compile(r'"Url"\s*:\s*"([^"]+-o-\d+)"', re.IGNORECASE)

        for script_text in script_texts:
            if not script_text or '"OptionId"' not in script_text or '"Url"' not in script_text:
                continue

            for raw_href in url_pattern.findall(script_text):
                href = raw_href.replace("\\/", "/").strip()
                if not self._is_product_url(href):
                    continue
                if href not in seen:
                    hrefs.append(href)
                    seen.add(href)

        return hrefs

    def _find_fallback_product_anchors(self, soup: BeautifulSoup) -> List[Any]:
        anchors: List[Any] = []
        seen_ids = set()
        for anchor in soup.select("a[href]"):
            href = anchor.get("href", "").strip()
            if not self._is_product_url(href):
                continue
            anchor_text = clean_text(anchor.get_text(" ", strip=True))
            if anchor.find("img") or not anchor_text:
                anchor_id = id(anchor)
                if anchor_id in seen_ids:
                    continue
                anchors.append(anchor)
                seen_ids.add(anchor_id)
        return anchors

    def _build_group_external_id(self, variant_ids: List[str], parsed_variant: Dict[str, Any]) -> str:
        numeric_ids = [int(value) for value in variant_ids if str(value).isdigit()]
        if numeric_ids:
            return f"lcw-{min(numeric_ids)}"
        group_sku = str(parsed_variant.get("group_sku") or parsed_variant.get("sku") or "").strip()
        if group_sku:
            return f"lcw-{group_sku.lower()}"
        return f"lcw-{parsed_variant.get('product_id')}"

    def _build_family_key(self, parsed_variant: Optional[Dict[str, Any]]) -> str:
        if not parsed_variant:
            return ""

        group_sku = str(parsed_variant.get("group_sku") or "").strip()
        if group_sku:
            return f"group_sku:{group_sku.lower()}"

        sku = str(parsed_variant.get("sku") or "").strip()
        if sku:
            return f"sku:{sku.lower()}"

        product_id = str(parsed_variant.get("product_id") or "").strip()
        if product_id:
            return f"product_id:{product_id}"

        return ""

    def _extract_price_text(self, text: str) -> str:
        match = self.PRICE_RE.search(text)
        return clean_text(match.group(1)) if match else ""

    def _extract_sku(self, text: str) -> str:
        match = re.search(r":\s*([A-Z0-9-]{5,})\s*-", text)
        return clean_text(match.group(1)) if match else ""

    def _extract_product_id(self, url: str) -> str:
        match = self.PRODUCT_PATH_RE.search(urlparse(url).path)
        return match.group(1) if match else url.rstrip("/").split("/")[-1]

    def _extract_category_id(self, url: str) -> str:
        match = self.CATEGORY_PATH_RE.search(urlparse(url).path)
        return match.group(1) if match else ""

    def _extract_category_name_from_url(self, category_url: str) -> str:
        slug = urlparse(category_url).path.strip("/").split("/")[-1]
        slug = re.sub(r"-t-\d+$", "", slug)
        return clean_text(slug.replace("-", " "))
