"""Общая память переводов: нормализация, батч, админка."""

from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.ai.models import AIProcessingLog, AIProcessingStatus, AITranslationMemory
from apps.ai.services import translation_memory as tm
from apps.catalog.models import Product

pytestmark = pytest.mark.django_db


def test_normalization_collapses_spaces_but_keeps_case():
    assert tm.normalize_source_text("  Günde  2\n kez ") == "Günde 2 kez"
    assert tm.source_hash("PARASETAMOL  500 mg") == tm.source_hash("PARASETAMOL 500 mg")
    assert tm.source_hash("Parasetamol") != tm.source_hash("PARASETAMOL")


def test_get_or_translate_batches_only_missing_and_stores_returned():
    tm.remember("medicine_paragraph", {"Günde 2 kez": {"ru": "2 раза в день", "en": "Twice daily"}})
    translator = Mock(
        return_value=(
            {"Aç karnına": {"ru": "Натощак", "en": "On an empty stomach"}},  # «Tok karnına» не прошёл проверки
            {"tokens": {"total": 50}, "cost_usd": 0.0001, "processing_time_ms": 3},
        )
    )

    found, usage = tm.get_or_translate(
        "medicine_paragraph", ["Günde  2 kez", "Aç karnına", "Tok karnına", "Aç karnına", ""], translator
    )

    translator.assert_called_once_with(["Aç karnına", "Tok karnına"])
    assert found == {
        "Günde 2 kez": {"ru": "2 раза в день", "en": "Twice daily"},
        "Aç karnına": {"ru": "Натощак", "en": "On an empty stomach"},
    }
    assert usage["cost_usd"] == 0.0001
    assert set(AITranslationMemory.objects.values_list("source_text", flat=True)) == {"Günde 2 kez", "Aç karnına"}
    assert AITranslationMemory.objects.get(source_text="Günde 2 kez").hits == 1


def test_namespaces_are_independent_and_existing_rows_not_overwritten():
    tm.remember("medicine_inn", {"Parasetamol": {"ru": "Парацетамол", "en": "Paracetamol"}})
    assert tm.lookup("product_description:1", ["Parasetamol"]) == {}
    assert tm.remember("medicine_inn", {"Parasetamol": {"ru": "Другое", "en": "Other"}}) == 0
    assert tm.lookup("medicine_inn", ["Parasetamol"])["Parasetamol"]["ru"] == "Парацетамол"


def test_lookup_respects_source_log_status():
    product = Product.objects.create(name="X", slug="tm-status")
    log = AIProcessingLog.objects.create(product=product, status=AIProcessingStatus.MODERATION, input_data={})
    tm.remember("product_description:1", {"Metin": {"ru": "Текст", "en": "Text"}}, log=log)
    accepted = (AIProcessingStatus.COMPLETED, AIProcessingStatus.APPROVED)

    assert tm.lookup("product_description:1", ["Metin"], log_statuses=accepted) == {}
    assert tm.lookup("product_description:1", ["Metin"])  # без фильтра — подходит


def test_admin_search_and_manual_edit_detaches_from_log(client, settings):
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    product = Product.objects.create(name="X", slug="tm-admin")
    log = AIProcessingLog.objects.create(product=product, status=AIProcessingStatus.MODERATION, input_data={})
    tm.remember("product_description:1", {"Klasik sneaker": {"ru": "Кроссовки", "en": "Sneakers"}}, log=log)
    entry = AITranslationMemory.objects.get()
    admin = get_user_model().objects.create_superuser("tm-admin", "tm@example.com", "tm-admin-password-123")
    client.force_login(admin)

    listing = client.get(reverse("admin:ai_aitranslationmemory_changelist"), {"q": "Klasik"})
    assert listing.status_code == 200 and "Klasik sneaker" in listing.content.decode()

    response = client.post(
        reverse("admin:ai_aitranslationmemory_change", args=[entry.pk]),
        {"ru_text": "Классические кроссовки", "en_text": "Classic sneakers"},
    )
    assert response.status_code == 302
    entry.refresh_from_db()
    assert entry.ru_text == "Классические кроссовки" and entry.source_log_id is None
    accepted = (AIProcessingStatus.COMPLETED, AIProcessingStatus.APPROVED)
    assert tm.lookup("product_description:1", ["Klasik sneaker"], log_statuses=accepted)
