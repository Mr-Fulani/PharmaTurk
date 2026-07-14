from types import SimpleNamespace

from apps.ai.services.content_generator import ContentGenerator


def _generator():
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.vector_store = None
    return generator


def test_category_context_contains_root_subcategory_and_full_path():
    root = SimpleNamespace(name="Головные уборы", slug="headwear", parent=None)
    child = SimpleNamespace(name="Кепки", slug="caps", parent=root)
    product = SimpleNamespace(category=child)

    context = _generator()._get_category_context(product)

    assert context["category"] == "Головные уборы"
    assert context["subcategory"] == "Кепки"
    assert context["current_category"] == "Кепки"
    assert context["category_path"] == "Головные уборы > Кепки"
    assert [item["slug"] for item in context["lineage"]] == ["headwear", "caps"]


def test_user_prompt_exposes_category_context_to_all_ru_en_content(monkeypatch):
    generator = _generator()
    category_context = {
        "category": "Головные уборы",
        "subcategory": "Кепки",
        "current_category": "Кепки",
        "category_path": "Головные уборы > Кепки",
        "lineage": [],
    }
    monkeypatch.setattr(
        generator,
        "_collect_input_data",
        lambda _product: {
            "name": "Erkek spor şapka",
            "description": "",
            "brand": None,
            "category_context": category_context,
        },
    )
    product = SimpleNamespace(category=None)

    prompt = generator._construct_user_prompt(product, {}, "full")

    assert '"category_path": "Головные уборы > Кепки"' in prompt
    assert "generated_title, generated_description, seo_title, seo_description и keywords" in prompt
    assert "«кепка» в RU и «cap» в EN" in prompt


def test_system_prompt_requires_language_specific_seo_and_category_semantics():
    prompt = _generator()._get_system_prompt()

    assert "ru — только на русском, en — только на английском" in prompt
    assert "RU/EN названиях, описаниях, SEO title, SEO description и keywords" in prompt
    assert "«şapka» в подкатегории «Кепки»" in prompt
