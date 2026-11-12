import importlib

import pytest
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.feedback import models as feedback_models
from apps.settings.models import HomeBlock, SiteAppearance

seed_migration = importlib.import_module("apps.settings.migrations.0005_seed_home_blocks")

APPEARANCE_URL = "/api/settings/appearance"
TESTIMONIALS_URL = "/api/feedback/testimonials-section-settings"


@pytest.fixture
def admin_client(client, settings):
    # Страницы админки рендерятся без collectstatic.
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    user = get_user_model().objects.create_superuser(
        username="appearance-admin", email="appearance-admin@example.com", password="appearance-admin-pass-2026"
    )
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_appearance_api_is_public_and_keeps_current_site_by_default():
    response = APIClient().get(APPEARANCE_URL)

    assert response.status_code == 200
    assert response.data["theme"] == "cream"
    # Порядок блоков — нынешний порядок главной; отзывы выключены, пока их не включили.
    assert [block["key"] for block in response.data["home_blocks"]] == seed_migration.HOME_BLOCKS
    assert [block["key"] for block in response.data["home_blocks"] if not block["is_enabled"]] == ["testimonials"]


@pytest.mark.django_db
def test_every_home_block_key_is_seeded():
    # Новый ключ блока без миграции данных не появится ни в админке, ни в API.
    assert sorted(seed_migration.HOME_BLOCKS) == sorted(HomeBlock.Key.values)
    assert set(HomeBlock.objects.values_list("key", flat=True)) == set(HomeBlock.Key.values)


@pytest.mark.django_db
def test_appearance_api_reflects_theme_order_and_hidden_blocks():
    appearance = SiteAppearance.load()
    appearance.theme = SiteAppearance.Theme.IZNIK
    appearance.save()
    HomeBlock.objects.filter(key="brands").update(is_enabled=False)
    HomeBlock.objects.filter(key="bestsellers").update(sort_order=5)

    data = APIClient().get(APPEARANCE_URL).data

    assert data["theme"] == "iznik"
    assert data["home_blocks"][0] == {"key": "bestsellers", "is_enabled": True}
    assert {"key": "brands", "is_enabled": False} in data["home_blocks"]


@pytest.mark.django_db
def test_site_appearance_is_a_single_record():
    SiteAppearance.load()
    SiteAppearance(theme=SiteAppearance.Theme.GREEN).save()

    assert SiteAppearance.objects.count() == 1
    assert SiteAppearance.load().theme == "green"


@pytest.mark.django_db
def test_testimonials_endpoint_follows_home_block():
    client = APIClient()
    assert client.get(TESTIMONIALS_URL).data == {"show_on_homepage": False}

    HomeBlock.objects.filter(key="testimonials").update(is_enabled=True)

    assert client.get(TESTIMONIALS_URL).data == {"show_on_homepage": True}


@pytest.mark.django_db
def test_seed_carries_over_testimonials_checkbox_and_keeps_admin_edits():
    feedback_models.TestimonialSectionSettings.objects.update_or_create(pk=1, defaults={"show_on_homepage": True})
    HomeBlock.objects.all().delete()

    seed_migration.seed_home_blocks(django_apps, None)

    assert HomeBlock.is_shown("testimonials") is True
    assert list(HomeBlock.objects.values_list("key", flat=True)) == seed_migration.HOME_BLOCKS

    # Повторный запуск не возвращает блоки, которые выключили в админке.
    HomeBlock.objects.filter(key="brands").update(is_enabled=False, sort_order=999)
    seed_migration.seed_home_blocks(django_apps, None)

    assert HomeBlock.objects.count() == len(seed_migration.HOME_BLOCKS)
    assert HomeBlock.objects.get(key="brands").sort_order == 999
    assert HomeBlock.is_shown("brands") is False


@pytest.mark.django_db
def test_home_blocks_admin_edits_checkbox_and_order_in_the_list(admin_client):
    changelist = reverse("admin:settings_homeblock_changelist")
    blocks = list(HomeBlock.objects.all())
    form = {
        "form-TOTAL_FORMS": len(blocks),
        "form-INITIAL_FORMS": len(blocks),
        "form-MIN_NUM_FORMS": 0,
        "form-MAX_NUM_FORMS": 1000,
        "_save": "Сохранить",
    }
    for index, block in enumerate(blocks):
        form[f"form-{index}-id"] = block.pk
        form[f"form-{index}-sort_order"] = 5 if block.key == "facts" else block.sort_order
        if block.is_enabled and block.key != "sourcing":
            form[f"form-{index}-is_enabled"] = "on"

    assert admin_client.get(changelist).status_code == 200
    assert admin_client.post(changelist, form).status_code == 302

    assert HomeBlock.objects.first().key == "facts"
    assert HomeBlock.is_shown("sourcing") is False
    # Набор блоков задан кодом: добавить или удалить блок в админке нельзя.
    assert admin_client.get(reverse("admin:settings_homeblock_add")).status_code == 403
    assert admin_client.post(reverse("admin:settings_homeblock_delete", args=[blocks[0].pk]), {"post": "yes"}).status_code == 403
    assert HomeBlock.objects.count() == len(blocks)


@pytest.mark.django_db
def test_theme_admin_opens_the_single_record(admin_client):
    response = admin_client.get(reverse("admin:settings_siteappearance_changelist"))

    assert response.status_code == 302
    assert response.url == reverse("admin:settings_siteappearance_change", args=[1])

    change = admin_client.post(response.url, {"theme": "green", "_save": "Сохранить"})

    assert change.status_code == 302
    assert SiteAppearance.load().theme == "green"
