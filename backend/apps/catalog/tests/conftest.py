import pytest

from apps.catalog.utils.currency_service import clear_rate_memo


@pytest.fixture(autouse=True)
def _isolate_rate_memo():
    """Мемо-кэш курсов — модульный dict; не даём ему протекать между тестами."""
    clear_rate_memo()
    yield
    clear_rate_memo()
