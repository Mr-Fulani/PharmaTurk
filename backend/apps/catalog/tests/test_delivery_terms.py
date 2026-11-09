"""Сроки доставки лекарств и БАДов (решение владельца 09.11.2026): правила замены и команда replace_delivery_terms."""
import importlib
import json

import pytest
from django.apps import apps as django_apps
from django.core.management import call_command

from apps.catalog.models import Category, CategoryTranslation, Product, ProductTranslation
from apps.catalog.services.delivery_terms import ORDER_SENTENCE, replace_terms


def test_code_sentences_and_other_wordings_are_replaced():
    # Описания карточек (короткая форма): прежнее предложение кода → ORDER_SENTENCE
    assert replace_terms("X из Турции. Заявка менеджеру, доставка 7–21 рабочий день.", short=True) == (
        "X из Турции. " + ORDER_SENTENCE["ru"]
    )
    assert replace_terms("X from Turkey. Send a request, delivery in 7–14 days.", supplements=True, short=True) == (
        "X from Turkey. " + ORDER_SENTENCE["en"]
    )
    assert replace_terms("Allow 7–21 working days.", short=True) == "Allow 3–14 days."
    # Тексты страниц: полная форма без диапазона впереди
    assert replace_terms("Заявка, доставка 7–21 рабочий день.") == "Заявка, доставка: авиа 3–7, наземная 7–14, морем 20–45 дней."
    assert replace_terms("Посылка идёт 7–21 рабочий день.") == "Посылка: авиа 3–7, наземная 7–14, морем 20–45 дней."
    assert replace_terms("Срок доставки — 7–21 рабочий день.") == "Срок доставки — авиа 3–7, наземная 7–14, морем 20–45 дней."
    assert replace_terms("Send a request; delivery takes 7–21 business days.") == (
        "Send a request; delivery: air 3–7, ground 7–14, sea 20–45 days."
    )
    assert replace_terms("A parcel spends 7–21 working days in transit.") == (
        "A parcel is in transit: air 3–7, ground 7–14, sea 20–45 days."
    )
    # «7–14 дней» — только у БАДов, и без «от 5 $»
    assert replace_terms("Доставка занимает 7–14 дней.") == "Доставка занимает 7–14 дней."
    assert replace_terms("Доставка занимает 7–14 дней, от 5 $.", supplements=True) == (
        "Доставка: авиа 3–7, наземная 7–14, морем 20–45 дней."
    )


def test_replacement_is_idempotent():
    for text in ("Посылка идёт 7–21 рабочий день.", "Доставка занимает 7–14 дней.", "Delivery in 7–14 days."):
        for short in (False, True):
            once = replace_terms(text, supplements=True, short=short)
            assert "7–21" not in once
            assert replace_terms(once, supplements=True, short=short) == once


def _product(product_type, slug, description):
    product = Product.objects.create(name=slug, slug=slug, product_type=product_type, price=10)
    # save() пересобирает SEO-поля — описание пишется так же, как его пишет команда
    Product.objects.filter(pk=product.pk).update(meta_description=description)
    product.refresh_from_db()
    return product


@pytest.mark.django_db
def test_command_shows_by_default_then_applies_and_restores(tmp_path):
    medicine = _product("medicines", "dt-med", "M из Турции. Заявка менеджеру, доставка 7–21 рабочий день.")
    supplement = _product("supplements", "dt-sup", "S из Турции. Заявка менеджеру, доставка 7–14 дней.")
    clothing = _product("clothing", "dt-clo", "Футболка. Доставка 7–14 дней, от 5 $.")
    translation = ProductTranslation.objects.create(product=medicine, locale="en", name="M")
    ProductTranslation.objects.filter(pk=translation.pk).update(
        meta_description="M. Send a request, delivery in 7–21 business days.",
    )

    call_command("replace_delivery_terms")
    medicine.refresh_from_db()
    assert "7–21" in medicine.meta_description

    backup = tmp_path / "terms.jsonl"
    call_command("replace_delivery_terms", "--apply", "--backup", str(backup))
    medicine.refresh_from_db()
    supplement.refresh_from_db()
    clothing.refresh_from_db()
    assert medicine.meta_description == "M из Турции. Заявка менеджеру, доставка 3–14 дней."
    assert supplement.meta_description == "S из Турции. Заявка менеджеру, доставка 3–14 дней."
    assert clothing.meta_description == "Футболка. Доставка 7–14 дней, от 5 $."
    assert ProductTranslation.objects.get(product=medicine).meta_description == "M. Send a request, delivery in 3–14 days."
    rows = [json.loads(line) for line in backup.read_text(encoding="utf-8").splitlines()]
    assert {row["model"] for row in rows} == {"catalog.Product", "catalog.ProductTranslation"}

    # Поле правили после записи — откат его не трогает
    Product.objects.filter(pk=supplement.pk).update(meta_description="Своё описание.")
    call_command("replace_delivery_terms", "--restore", str(backup))
    medicine.refresh_from_db()
    supplement.refresh_from_db()
    assert medicine.meta_description == "M из Турции. Заявка менеджеру, доставка 7–21 рабочий день."
    assert supplement.meta_description == "Своё описание."


def test_apply_requires_backup():
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("replace_delivery_terms", "--apply")


@pytest.mark.django_db
def test_category_migration_changes_only_medicine_and_supplement_trees():
    migration = importlib.import_module('apps.catalog.migrations.0239_medicines_supplements_delivery_terms')
    medicines = Category.objects.update_or_create(slug="medicines", defaults={"name": "Медикаменты"})[0]
    child = Category.objects.update_or_create(slug="dt-cardio", defaults={"name": "Сердце", "parent": medicines})[0]
    supplements = Category.objects.update_or_create(slug="supplements", defaults={"name": "БАДы"})[0]
    clothing = Category.objects.update_or_create(slug="dt-clothing", defaults={"name": "Одежда"})[0]

    def translation(category, **fields):
        return CategoryTranslation.objects.update_or_create(
            category=category, locale="ru", defaults={"name": category.name, **fields},
        )[0]

    cardio = translation(
        child, meta_description="Заявка, доставка 7–21 рабочий день.", seo_text="Посылка идёт 7–21 рабочий день.",
    )
    supp = translation(supplements, seo_text="Доставка занимает 7–14 дней.")
    clothes = translation(clothing, seo_text="Доставка занимает 7–14 дней.")

    migration.forwards(django_apps, None)
    for row in (cardio, supp, clothes):
        row.refresh_from_db()
    assert cardio.meta_description == "Заявка, доставка 3–14 дней."
    assert cardio.seo_text == "Посылка: авиа 3–7, наземная 7–14, морем 20–45 дней."
    assert supp.seo_text == "Доставка: авиа 3–7, наземная 7–14, морем 20–45 дней."
    assert clothes.seo_text == "Доставка занимает 7–14 дней."


@pytest.mark.django_db
def test_category_migration_replaces_home_banner_subtitle():
    from apps.catalog.models import Banner

    migration = importlib.import_module('apps.catalog.migrations.0239_medicines_supplements_delivery_terms')
    banner = Banner.objects.create(title="Доставка из Турции", description="7–21 рабочий день: авиа, авто или морем")
    migration.forwards(django_apps, None)
    banner.refresh_from_db()
    assert banner.description == "авиа 3–7, наземная 7–14, морем 20–45 дней"
