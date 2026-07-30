import pytest

from apps.catalog.constants import FURNITURE_SUBCATEGORIES
from apps.catalog.management.commands.seed_catalog_data import Command
from apps.catalog.models import Category, CategoryTranslation


def test_seed_command_has_isolated_furniture_only_mode():
    parser = Command().create_parser("manage.py", "seed_catalog_data")

    options = vars(parser.parse_args(["--furniture-only"]))

    assert options["furniture_only"] is True
    assert options["categories_only"] is False


def test_furniture_seed_tree_has_expected_top_level_and_unique_slugs():
    top_level_slugs = [item[2] for item in FURNITURE_SUBCATEGORIES]
    all_slugs = top_level_slugs + [
        child[2]
        for item in FURNITURE_SUBCATEGORIES
        for child in item[5]
    ]

    assert top_level_slugs == [
        "living-room",
        "bedroom",
        "kitchen-dining",
        "office",
        "kids-furniture",
        "storage-furniture",
        "bathroom-furniture",
        "outdoor-furniture",
    ]
    assert len(all_slugs) == len(set(all_slugs))


@pytest.mark.django_db
def test_furniture_seed_is_idempotent_and_preserves_existing_categories():
    # Часть окружений создаёт дерево мебели data-миграцией. Подготавливаем
    # ручные данные поверх уже существующих строк, чтобы тест проверял именно
    # идемпотентность команды, а не порядок миграций.
    root, _ = Category.objects.get_or_create(slug="furniture")
    root.name = "Мебель вручную"
    root.description = "Описание корня вручную"
    root.is_active = False
    root.sort_order = 77
    root.save()
    living_room, _ = Category.objects.get_or_create(slug="living-room")
    living_room.name = "Ручное название"
    living_room.description = "Ручное описание"
    living_room.parent = root
    living_room.is_active = False
    living_room.sort_order = 91
    living_room.save()
    CategoryTranslation.objects.create(
        category=living_room,
        locale="ru",
        name="Ручной перевод",
        description="Ручное описание перевода",
    )

    command = Command()
    command._seed_root_categories()
    command._seed_furniture_subcategories()
    count_after_first_run = Category.objects.filter(parent=root).count()
    command._seed_furniture_subcategories()

    root.refresh_from_db()
    living_room.refresh_from_db()
    translation = CategoryTranslation.objects.get(category=living_room, locale="ru")

    assert root.name == "Мебель вручную"
    assert root.description == "Описание корня вручную"
    assert root.is_active is False
    assert root.sort_order == 77
    assert living_room.name == "Ручное название"
    assert living_room.description == "Ручное описание"
    assert living_room.is_active is False
    assert living_room.sort_order == 91
    assert translation.name == "Ручной перевод"
    assert translation.description == "Ручное описание перевода"
    assert Category.objects.filter(parent=root).count() == count_after_first_run
    assert Category.objects.get(slug="sofa-beds").parent == living_room
    assert Category.objects.get(slug="bathroom-cabinets").parent.slug == "bathroom-furniture"
