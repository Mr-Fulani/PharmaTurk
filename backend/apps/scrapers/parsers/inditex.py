"""Общий контракт витрин Inditex, отличных от Zara.

Сайты используют близкий server payload, но имеют разные URL и отдельные
защитные контуры. Адаптеры наследуют только разбор данных; имя, домены,
URL-контракт и HTTP-сессия у каждого источника свои.
"""

import re
from abc import abstractmethod
from typing import Any, Dict
from urllib.parse import urlencode, urljoin, urlparse, urlunparse

from .zara import ZaraParser


class InditexSiblingParser(ZaraParser):
    """Переиспользуем проверенный payload parser без регистрации base-класса."""

    PRODUCT_PATH_RE = re.compile(
        r"(?:-c\d+p\d+(?:\.html)?|-l\d+)(?:$|[?#])",
        re.IGNORECASE,
    )
    CATEGORY_PATH_RE = re.compile(r"-n\d+(?:\.html)?(?:$|[?#])", re.IGNORECASE)
    MARKETING_PATH_RE = re.compile(r"(?!x)x")
    VIEW_PAYLOAD_MARKER = (
        "window.bershka.viewPayload = ",
        "window.pullandbear.viewPayload = ",
        "window.massimodutti.viewPayload = ",
        "window.inditex.viewPayload = ",
        "viewPayload = ",
    )
    PRODUCT_URL_STYLE = "c0p"

    @abstractmethod
    def get_name(self) -> str:
        raise NotImplementedError

    @classmethod
    def is_zara_product_url(cls, url: str) -> bool:
        parsed = urlparse(url)
        return bool(cls.PRODUCT_PATH_RE.search(parsed.path or url)) or bool(
            "pelement" in parsed.query and re.search(r"-l\d+", parsed.path, re.I)
        )

    @classmethod
    def is_zara_category_url(cls, url: str) -> bool:
        return bool(cls.CATEGORY_PATH_RE.search(urlparse(url).path or url))

    def _build_product_url(self, component: Dict[str, Any], source_url: str) -> str:
        # У sibling-витрин payload часто уже содержит канонический URL.
        seo = component.get("seo") if isinstance(component.get("seo"), dict) else {}
        for candidate in (
            seo.get("url"),
            component.get("url"),
            component.get("productUrl"),
            component.get("canonicalUrl"),
        ):
            if candidate:
                return self._canonical_url(urljoin(source_url, str(candidate)))
        keyword = str(seo.get("keyword") or "").strip(" /")
        product_id = str(seo.get("seoProductId") or component.get("id") or "").strip()
        if not keyword or not product_id:
            return ""
        parsed = urlparse(source_url)
        path_parts = [part for part in parsed.path.split("/") if part]
        locale_prefix = f"/{path_parts[0]}" if path_parts else "/tr"
        if self.PRODUCT_URL_STYLE == "l":
            element_id = str(component.get("id") or product_id)
            return urlunparse(
                parsed._replace(
                    path=f"{locale_prefix}/{keyword}-l{product_id}",
                    query=urlencode({"pelement": element_id}),
                    fragment="",
                )
            )
        return urlunparse(
            parsed._replace(
                path=f"{locale_prefix}/{keyword}-c0p{product_id}.html",
                query="",
                fragment="",
            )
        )
