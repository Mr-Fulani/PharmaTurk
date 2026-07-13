"""Парсер турецкой витрины Bershka."""

from typing import List

from .inditex import InditexSiblingParser


class BershkaParser(InditexSiblingParser):
    SOURCE_PREFIX = "bershka"
    SOURCE_LABEL = "Bershka"
    BRAND_NAME = "Bershka"
    WARMUP_URL = "https://www.bershka.com/tr/"

    def __init__(self, base_url: str = "https://www.bershka.com/tr/", **kwargs):
        super().__init__(base_url=base_url, **kwargs)

    def get_name(self) -> str:
        return "bershka"

    def get_supported_domains(self) -> List[str]:
        return ["bershka.com", "www.bershka.com"]
