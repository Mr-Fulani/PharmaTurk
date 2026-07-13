"""Парсер турецкой витрины Massimo Dutti."""

from typing import List

from .inditex import InditexSiblingParser


class MassimoDuttiParser(InditexSiblingParser):
    SOURCE_PREFIX = "massimodutti"
    SOURCE_LABEL = "Massimo Dutti"
    BRAND_NAME = "Massimo Dutti"
    WARMUP_URL = "https://www.massimodutti.com/tr/"
    PRODUCT_URL_STYLE = "l"

    def __init__(self, base_url: str = "https://www.massimodutti.com/tr/", **kwargs):
        super().__init__(base_url=base_url, **kwargs)

    def get_name(self) -> str:
        return "massimodutti"

    def get_supported_domains(self) -> List[str]:
        return ["massimodutti.com", "www.massimodutti.com"]
