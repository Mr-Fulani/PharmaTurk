"""Тесты авто-обнаружения парсеров в реестре."""

from apps.scrapers.base.scraper import BaseScraper
from apps.scrapers.parsers import registry


EXPECTED_PARSERS = {
    "ilacabak",
    "zara",
    "instagram",
    "ummaland",
    "ilacfiyati",
    "ikea",
    "lcw",
    "flo",
    "massimodutti",
    "bershka",
    "pullandbear",
}


def test_autodiscovery_registers_all_known_parsers():
    registry.register_default_parsers()
    names = set(registry.get_all_parsers().keys())
    assert EXPECTED_PARSERS <= names


def test_autodiscovery_is_idempotent():
    registry.register_default_parsers()
    first = registry.get_all_parsers()
    registry.register_default_parsers()
    second = registry.get_all_parsers()
    assert set(first) == set(second)


def test_registered_classes_are_concrete_base_scrapers():
    for parser_class in registry.get_all_parsers().values():
        assert issubclass(parser_class, BaseScraper)
        assert parser_class is not BaseScraper


def test_zara_resolves_by_domain_after_autodiscovery():
    registry.register_default_parsers()
    parser_class = registry.get_parser("https://www.zara.com/tr/tr/kadin-elbiseler-l1066.html")
    assert parser_class is not None
    assert parser_class().get_name() == "zara"


def test_inditex_sibling_parsers_resolve_by_config_name():
    registry.register_default_parsers()

    assert registry.get_parser("massimodutti")().get_name() == "massimodutti"
    assert registry.get_parser("bershka")().get_name() == "bershka"
    assert registry.get_parser("pullandbear")().get_name() == "pullandbear"


def test_unknown_parser_name_does_not_resolve_to_an_unrelated_domain():
    registry.register_default_parsers()

    assert registry.get_parser("unknown-inditex-shop") is None


def test_bare_registered_domain_still_resolves():
    registry.register_default_parsers()

    parser_class = registry.get_parser("zara.com")

    assert parser_class is not None
    assert parser_class().get_name() == "zara"


def test_lookalike_domain_does_not_match_registered_domain():
    registry.register_default_parsers()

    assert registry.get_parser("https://notzara.com/product") is None
