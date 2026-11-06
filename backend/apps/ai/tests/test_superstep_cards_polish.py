"""Карточки SuperStep 06.11.2026: 115 из 1 488 с ошибками описания (номер товара в комментарии).

Правка — apps/ai/services/rules/polish.py: одинаково для ответа модели и для описания из памяти.
"""

from types import SimpleNamespace

import pytest

from apps.ai.services.rules.facts import clean_source_text
from apps.ai.services.rules.polish import polish_description, turkish_leftovers
from apps.ai.services.rules.vocab import translate_shoe_material


@pytest.mark.parametrize(
    "text, expected",
    [
        # Висящий хвост после вырезанной «воды»: срезается, пустое по смыслу предложение уходит.
        ("Прямой однотонный дизайн подходит для.", ""),  # 26918
        ("Подходит для активного отдыха на природе и.", "Подходит для активного отдыха на природе."),  # 26927
        ("Кремовый цвет нейтрален и.", "Кремовый цвет нейтрален."),  # 27101
        ("Белый цвет нейтрален и.", "Белый цвет нейтрален."),  # 28452
        ("Белый цвет нейтрален и легко сочетается с повседневной одеждой.", "Белый цвет нейтрален."),
        ("Модель подходит как для спорта, так и.", ""),  # 27143
        ("Модель подходит как для спорта, так и для повседневной носки.", ""),
        (
            "Однотонный белый цвет подходит как для мальчиков, так и для девочек и.",  # 27016
            "Однотонный белый цвет подходит как для мальчиков, так и для девочек.",
        ),
        (
            "Модель сочетает натуральную кожу премиального качества с деталями из замши и.",  # 27113
            "Модель сочетает натуральную кожу премиального качества с деталями из замши.",
        ),
        (
            "Модель создана для активного городского ритма и отличается сдержанным бежевым оттенком, который.",  # 27233
            "Модель создана для активного городского ритма и отличается сдержанным бежевым оттенком.",
        ),
        ("Модель выполнена в современном минималистичном дизайне и.", "Модель выполнена в современном минималистичном дизайне."),  # 28360
        ("Мягкая и дышащая ткань, модель подходит для.", "Мягкая и дышащая ткань."),  # 28340
        ("Белая цветовая гамма делает модель универсальной и.", ""),  # 27176
        ("Кроссовки для повседневной носки и бега.", "Кроссовки для бега."),
        # Ответ модели, не память: правка однозначная.
        ("Ергономичная конструкция обеспечивает комфорт.", "Эргономичная конструкция обеспечивает комфорт."),  # 27135
        ("Лёгкий ергономичный стелька.", "Лёгкий эргономичный стелька."),  # 27357
        ("Бренд Lacoste. Кроя regular fit — садится по фигуре.", "Бренд Lacoste. Крой regular fit — садится по фигуре."),  # 28265
        ("Жилет тёплый. Кроя без рукавов не ограничивает движения рук.", "Жилет тёплый. Крой без рукавов не ограничивает движения рук."),  # 28313
        ("Сделаны из файла, TPU и синтетической кожи.", "Сделаны из сетки, TPU и синтетической кожи."),  # 27526
        ("Лёгкая лёгкая подошва обеспечивает удобство.", "Лёгкая подошва обеспечивает удобство."),  # 27434
        ("Кроссовки из белого цвета с логотипом.", "Кроссовки белого цвета с логотипом."),  # 27225
        ("Низкий голенище не давит на лодыжку.", "Низкое голенище не давит на лодыжку."),  # 27929
        # Турецкий оригинал в скобках или кавычках после перевода.
        ("Вырез — круглый (bisiklet yaka). Дизайн с монограммой.", "Вырез — круглый. Дизайн с монограммой."),  # 27993
        ("Классическая горловина-«bisiklet yaka» сохраняет силуэт.", "Классическая горловина сохраняет силуэт."),  # 27988
        ("Куртка с отложным воротником (Dik Yaka) тёмно-синего (lacivert) цвета.", "Куртка с отложным воротником тёмно-синего цвета."),  # 28253
        # Не трогается: технология и состав в скобках, «так и» в середине.
        ("Подошва (DNA LOFT v2) мягкая. Состав (100% полиэстер).", "Подошва (DNA LOFT v2) мягкая. Состав (100% полиэстер)."),
    ],
)
def test_polish_ru(text, expected):
    assert polish_description(text, "ru") == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        # Описания FLO/IKEA/LC Waikiki (логи прода): вырезка «воды» не ломает предложение.
        ("Модель с надписями, подходит для повседневной носки и добавляет образу спортивный характер.",  # 21145
         "Модель с надписями добавляет образу спортивный характер."),
        ("Кроссовки Adidas VL COURT BASE органично сочетаются с разными стилями жизни и служат модным акцентом образа.",  # 10686
         "Кроссовки Adidas VL COURT BASE служат модным акцентом образа."),
        ("Лаконичный дизайн и удобная конструкция подходят как для повседневной носки, так и для особых случаев.",  # 10686
         "Лаконичный дизайн и удобная конструкция подходят для особых случаев."),
        ("Модель имеет современный дизайн и подходит для повседневной носки в городе.", "Модель имеет современный дизайн."),  # 10805
        ("Изготовлена из 100% хлопка, лёгкая и комфортная, подходит для повседневной носки, в том числе в жаркую погоду.",  # 20557
         "Изготовлена из 100% хлопка, лёгкая и комфортная."),
        ("Ткань лёгкая и мягкая, подходит для повседневной носки и легко сочетается с другими вещами в гардеробе.",  # 20146
         "Ткань лёгкая и мягкая."),
        ("Средняя толщина делает его подходящим для повседневной носки.", ""),  # 449
        ("Подходит для повседневного использования, особенно в жаркую погоду или в офисе.", ""),  # 4609
        ("Базовая модель, которую удобно сочетать с джинсами и брюками.", ""),  # 21012
        # «В сочетании с …» у IKEA — факт, не «вода» (15334).
        ("В сочетании с другими каркасами PAX позволяет использовать весь угол для хранения.",
         "В сочетании с другими каркасами PAX позволяет использовать весь угол для хранения."),
    ],
)
def test_polish_other_sources_keep_grammar(text, expected):
    assert polish_description(text, "ru") == expected


def test_polish_keeps_tags_and_drops_empty_ones():
    text = "<p>Модель подходит для повседневной носки.</p><ul><li>Кремовый цвет нейтрален и.</li><li>Подошва EVA.</li></ul>"
    assert polish_description(text, "ru") == "<ul><li>Кремовый цвет нейтрален.</li><li>Подошва EVA.</li></ul>"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Made of cotton. Ideal for everyday wear. It pairs well with jeans.", "Made of cotton."),
        ("The cream color is neutral and.", "The cream color is neutral."),
        ("Both upper and sole are durable.", "Both upper and sole are durable."),
    ],
)
def test_polish_en(text, expected):
    assert polish_description(text, "en") == expected


@pytest.mark.parametrize(
    "text, identity, leftovers",
    [
        ("Мужская куртка Lacoste, из Şişme (надувная/утеплённая) модели.", "Lacoste", ["Şişme"]),  # 28236
        ("Поло из коллекции House of Superstep X Lacoste Kapsül Koleksiyon.", "Lacoste", ["Kapsül", "Koleksiyon"]),  # 28198
        ("Внешняя подошва: Zero Gravity Köpük.", "On", ["Köpük"]),  # 27717
        ("Свитшот в canlı yeşil цвете — ярком зелёном.", "Lacoste", ["canlı", "yeşil"]),  # 28061
        ("Lacoste Kadın Beyaz Powercourt — женские белые кроссовки.", "Lacoste Powercourt", ["Kadın", "Beyaz"]),  # 27255
        ("Посадка regular fit, slim fit, classic fit, crew neck.", "Lacoste", []),  # английские слова — не ошибка
        ("Кроссовки İnci белые.", "İnci", []),  # бренд с турецкой буквой
    ],
)
def test_turkish_leftovers_in_ru_description(text, identity, leftovers):
    assert turkish_leftovers(text, identity) == leftovers


@pytest.mark.django_db
def test_turkish_leftover_sends_rule_log_to_moderation():
    from apps.ai.services.quality_checker import get_moderation_reasons

    log = SimpleNamespace(
        category_confidence=None,
        input_data={"product_type": "clothing"},
        generated_title="Мужская куртка Lacoste Classic Fit",
        generated_description="<p>Мужская куртка Lacoste Classic Fit с капюшоном, серого цвета, утеплённая (Şişme — «надувная», «стёганая» по смыслу модели). Капюшон регулируется.</p>",
        extracted_attributes={},
        raw_llm_response={"rule_content": {"description_source": "llm", "facts": {"brand": "Lacoste", "model": "Classic Fit"}}},
        product=None,
    )
    assert "description_untranslated" in get_moderation_reasons(log)  # 28239
    # БАДы: «Otacı», «İmuneks» в описании — названия, а не непереведённый текст.
    log.input_data = {"product_type": "supplements"}
    assert "description_untranslated" not in get_moderation_reasons(log)


def test_superstep_template_fields_with_turkish_name_are_cut():
    # 28197, 28219, 28329: «Название модели: Lacoste Sport Kadın Relaxed Fit Beyaz Şort» в описании.
    text = (
        "Ürün Özellikleri Marka: Lacoste. Ürün tipi: Şort. Ürün adı: Lacoste Sport Kadın Relaxed Fit Beyaz Şort. "
        "Kalıp: Relaxed Fit. Bakım Nemli bezle silin."
    )
    cleaned = clean_source_text(text, "superstep")
    assert "Kadın" not in cleaned and "Marka" not in cleaned and "Ürün tipi" not in cleaned
    assert "Kalıp: Relaxed Fit." in cleaned and "Nemli bezle silin" in cleaned
    flat = "Teknik Özellikler Marka: Lacoste Ürün adı: Lacoste AG-LT23 Ultra Kadın Mavi Sneaker Alt grup: Spor Ayakkabı Renk: Mavi"
    assert clean_source_text(flat, "superstep") == "Teknik Özellikler Renk: Mavi"
    assert clean_source_text(text, "flo") == text  # другие источники не трогаются


def test_file_material_is_mesh():
    assert translate_shoe_material("File/TPU") == ("сетка, термополиуретан", "mesh, TPU")  # 27526


@pytest.mark.django_db
def test_pipeline_polishes_model_answer_and_remembers_it_raw():
    from unittest.mock import Mock

    from apps.ai.models import AITranslationMemory
    from apps.ai.services.content_generator import ContentGenerator
    from apps.ai.services.result_applier import AIResultApplier
    from apps.catalog.models import Category, ClothingProduct, Product

    category, _ = Category.objects.update_or_create(slug="t-shirts", defaults={"name": "Футболки", "is_active": True})
    name = "Lacoste Erkek Relaxed Fit Bisiklet Yaka T-Shirt"
    source = "Pamuklu kumaştan üretilen rahat kesim tişört. Yumuşak dokusu gün boyu konfor sağlar. Bisiklet yaka detayı."
    product = Product.objects.create(
        name=name, slug="polish-pipeline-tee", product_type="clothing", category=category, description=source,
        external_id="superstep-POLISH1",
    )
    ClothingProduct.objects.update_or_create(base_product=product, defaults={"name": name, "slug": "polish-pipeline-tee"})
    raw_ru = (
        "<p>Футболка из мягкого хлопка. Ергономичный крой не стесняет движений. "
        "Кремовый цвет нейтрален и легко сочетается с джинсами. Вырез круглый (bisiklet yaka).</p>"
    )
    content = {"ru": {"generated_description": raw_ru}, "en": {"generated_description": "<p>Soft cotton tee. Ideal for everyday wear.</p>"}}
    llm = SimpleNamespace(model="test-model", generate_content=Mock(return_value={
        "content": content, "tokens": {"prompt": 400, "completion": 300, "total": 700, "cached": 0},
        "cost_usd": 0.0003, "processing_time_ms": 5,
    }))
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.vector_store, generator.result_applier, generator.llm = None, AIResultApplier(), llm

    log = generator.process_product(product.id, options={"analyze_images": False, "force": True})

    assert "Эргономичный крой" in log.generated_description
    assert "сочетается" not in log.generated_description and "bisiklet" not in log.generated_description
    assert "Кремовый цвет нейтрален." in log.generated_description
    memory = AITranslationMemory.objects.get(source_log=log)
    assert memory.ru_text == raw_ru  # в памяти — ответ модели как есть: правка действует при каждом чтении


@pytest.mark.django_db
def test_polish_product_memory_shows_then_applies_with_backup(tmp_path):
    import json
    from io import StringIO

    from django.core.management import call_command
    from django.core.management.base import CommandError

    from apps.ai.models import AITranslationMemory
    from apps.ai.services.translation_memory import source_hash

    def row(namespace, source, ru):
        return AITranslationMemory.objects.create(
            namespace=namespace, source_hash=source_hash(source), source_text=source, ru_text=ru, en_text="Soft tee."
        )

    bad = row("product_description:1", "kaynak 1", "<p>Мягкая ткань. Ергономичный крой. Кремовый цвет нейтрален и.</p>")
    clean = row("product_description:1", "kaynak 2", "<p>Мягкая ткань.</p>")
    other = row("medicine_paragraph", "kaynak 3", "Ергономичный")  # не описания товаров — не трогаем

    call_command("polish_product_memory", stdout=StringIO())
    bad.refresh_from_db()
    assert "Ергономичный" in bad.ru_text  # без --apply ничего не пишется
    with pytest.raises(CommandError):
        call_command("polish_product_memory", "--apply", stdout=StringIO())

    backup = tmp_path / "pdmem.json"
    call_command("polish_product_memory", "--apply", "--backup", str(backup), stdout=StringIO())

    for row_ in (bad, clean, other):
        row_.refresh_from_db()
    assert bad.ru_text == "<p>Мягкая ткань. Эргономичный крой. Кремовый цвет нейтрален.</p>"
    assert clean.ru_text == "<p>Мягкая ткань.</p>" and other.ru_text == "Ергономичный"
    assert json.loads(backup.read_text()) == [
        {"pk": bad.pk, "ru_text": "<p>Мягкая ткань. Ергономичный крой. Кремовый цвет нейтрален и.</p>", "en_text": "Soft tee."}
    ]
