from apps.catalog.catalog_representation import LocalizedSeoMethodsMixin
from apps.catalog.serializers import _LocalizedSeoMethodsMixin


def test_legacy_localized_seo_mixin_is_public_contract_alias():
    assert _LocalizedSeoMethodsMixin is LocalizedSeoMethodsMixin
