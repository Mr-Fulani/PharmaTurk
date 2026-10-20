from io import StringIO

import pytest
from django.core.management import call_command

from apps.catalog.models import Category, Product
from apps.scrapers.parsers.lcw import LcwParser

PAGE = """
<html><head>
<title>LCW ACCESSORIES Erkek Deodorant 150 ml - 9W1948Z8-CRP | LCW</title>
<meta property="og:title" content="Deodorant - Markalar - 319,89 TL" />
</head><body></body></html>
"""


@pytest.fixture
def broken(db, monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)
    monkeypatch.setattr(LcwParser, "_make_request", lambda self, url, **kwargs: PAGE)
    category = Category.objects.create(name="Парфюм", slug="lcw-names-perfume")
    return Product.objects.create(
        name="Deodorant - Markalar - 319,89 TL", slug="lcw-deodorant-4101563", category=category,
        product_type="perfumery", price=319.89, currency="TRY", external_id="lcw-4101563",
        external_url="https://www.lcw.com/erkek-deodorant-150-ml-renksiz-o-4101563",
        external_data={"source": "lcw"},
    )


def test_dry_run_reports_new_name_without_changes(broken):
    out = StringIO()
    call_command("repair_lcw_names", stdout=out)
    broken.refresh_from_db()
    assert broken.name == "Deodorant - Markalar - 319,89 TL"
    assert "LCW ACCESSORIES Erkek Deodorant 150 ml - 9W1948Z8-CRP" in out.getvalue()


def test_apply_replaces_marketing_name(broken):
    call_command("repair_lcw_names", "--apply", stdout=StringIO())
    broken.refresh_from_db()
    assert broken.name == "LCW ACCESSORIES Erkek Deodorant 150 ml - 9W1948Z8-CRP"
    assert broken.domain_item.name == broken.name
