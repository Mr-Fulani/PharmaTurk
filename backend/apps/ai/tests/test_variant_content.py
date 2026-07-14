from types import SimpleNamespace

from apps.ai.services.content_generator import ContentGenerator


class _SaveableVariant(SimpleNamespace):
    def save(self, update_fields=None):
        self.saved_update_fields = update_fields


def _generator_without_dependencies():
    return ContentGenerator.__new__(ContentGenerator)


def test_variant_title_normalization_uses_shared_color_vocabulary():
    generator = _generator_without_dependencies()
    content = {
        "ru": {"generated_title": "YAPILI BERE - Kahverengi"},
        "en": {"generated_title": "YAPILI BERE - Kahverengi"},
    }

    result = generator._normalize_variant_generated_titles(
        content,
        {"color": "Kahverengi", "suggested_titles": {}},
    )

    assert result["ru"]["generated_title"] == "YAPILI BERE - Коричневый"
    assert result["en"]["generated_title"] == "YAPILI BERE - Brown"


def test_color_and_sizes_only_variant_skips_separate_llm_processing():
    generator = _generator_without_dependencies()
    variant = _SaveableVariant(external_data={})
    generator._collect_variant_input_data = lambda current: {
        "color": "Kahverengi",
        "size_options": ["Standart"],
        "variant_description": "",
        "variant_snapshot": {},
    }

    result = generator.process_variant_content(variant)

    assert result["status"] == "skipped"
    assert result["reason"] == "insufficient_variant_specific_data"
    assert variant.external_data["ai_variant_content"] == result
    assert variant.saved_update_fields == ["external_data"]


def test_variant_specific_snapshot_still_requires_separate_processing():
    generator = _generator_without_dependencies()
    variant = _SaveableVariant(external_data={})
    generator._collect_variant_input_data = lambda current: {
        "color": "Kahverengi",
        "size_options": [],
        "variant_description": "",
        "variant_snapshot": {"material": "wool"},
    }
    generator.llm = SimpleNamespace(
        model="test-model",
        generate_content=lambda **kwargs: {
            "content": {
                "ru": {
                    "generated_title": "Берет - Kahverengi",
                    "generated_description": "Шерстяной вариант",
                },
                "en": {
                    "generated_title": "Beret - Kahverengi",
                    "generated_description": "Wool variant",
                },
            },
            "tokens": 10,
            "cost_usd": 0.001,
            "processing_time_ms": 5,
        },
    )
    generator._sanitize_ai_content = lambda content, input_data, variant_mode=False: content

    result = generator.process_variant_content(variant)

    assert result["status"] == "completed"
    assert result["draft"]["ru"]["generated_title"] == "Берет - Коричневый"
    assert result["draft"]["en"]["generated_title"] == "Beret - Brown"
