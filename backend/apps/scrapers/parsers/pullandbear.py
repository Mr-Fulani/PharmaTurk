"""Парсер турецкой витрины Pull&Bear."""

from typing import List

from .inditex import InditexSiblingParser


class PullAndBearParser(InditexSiblingParser):
    SOURCE_PREFIX = "pullandbear"
    SOURCE_LABEL = "Pull&Bear"
    BRAND_NAME = "Pull&Bear"
    WARMUP_URL = "https://www.pullandbear.com/tr/"

    def __init__(self, base_url: str = "https://www.pullandbear.com/tr/", **kwargs):
        super().__init__(base_url=base_url, **kwargs)

    def get_name(self) -> str:
        return "pullandbear"

    def get_supported_domains(self) -> List[str]:
        return ["pullandbear.com", "www.pullandbear.com"]
