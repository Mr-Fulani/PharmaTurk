"""parse_categories для обхода всего сайта: фрагменты настоящих ответов от 21.10.2026.

Каждый адрес из списка должен открываться категорийным режимом своего парсера,
а сбой источника — давать ошибку, а не пустой «успешный» список.
"""

import pytest

from apps.scrapers.base.scraper import SiteCategoriesError
from apps.scrapers.parsers.flo import FloParser

# --- общий хвост -----------------------------------------------------------


def test_site_categories_dedupes_by_url_and_sets_source():
    parser = FloParser()

    categories = parser._site_categories(
        [
            {"name": "Bot", "url": "https://www.flo.com.tr/bot", "external_id": "21"},
            {"name": "Bot (menü)", "url": "https://www.flo.com.tr/bot", "external_id": "21"},
            {"name": "Sneaker", "url": "https://www.flo.com.tr/sneaker", "external_id": 26},
        ]
    )

    assert categories == [
        {"name": "Bot", "url": "https://www.flo.com.tr/bot", "external_id": "21", "source": "flo"},
        {
            "name": "Sneaker",
            "url": "https://www.flo.com.tr/sneaker",
            "external_id": "26",
            "source": "flo",
        },
    ]


def test_site_categories_is_bounded():
    parser = FloParser()
    parser.MAX_SITE_CATEGORIES = 2

    categories = parser._site_categories(
        {"name": str(index), "url": f"https://www.flo.com.tr/c-{index}"} for index in range(5)
    )

    assert [row["name"] for row in categories] == ["0", "1"]


def test_site_categories_empty_list_is_source_error():
    with pytest.raises(SiteCategoriesError, match="flo"):
        FloParser()._site_categories([])
