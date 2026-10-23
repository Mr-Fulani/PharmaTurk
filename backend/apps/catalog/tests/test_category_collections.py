"""Посадочные страницы медикаментов: SEO категорий, подборки и их товары."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory

from apps.catalog.models import (
    Category,
    CategoryCollection,
    CategoryCollectionTranslation,
    CategoryTranslation,
    MedicineProduct,
    Product,
)
from apps.catalog.views import MedicineProductViewSet


def _medicine_slugs(**params):
    view = MedicineProductViewSet()
    view.request = Request(APIRequestFactory().get('/api/catalog/medicines/products', params))
    view.action = 'list'
    return set(view.get_queryset().values_list('slug', flat=True))


@pytest.fixture
def medicines(monkeypatch):
    monkeypatch.setattr(Product, 'update_currency_prices', lambda *args, **kwargs: None)

    root = Category.objects.create(name='Medicine', slug='medicines')
    respiratory = Category.objects.create(name='Respiratory', slug='respiratory-ent', parent=root)
    painkillers = Category.objects.create(name='Pain', slug='painkillers', parent=root)
    other_root = Category.objects.create(name='Clearance', slug='clearance')

    def create(slug, category, *, name=None, atc='', form=''):
        base = Product.objects.create(
            name=name or slug.upper(),
            slug=slug,
            product_type='medicines',
            category=category,
            price=Decimal('10.00'),
            currency='TRY',
            is_active=True,
        )
        MedicineProduct.objects.filter(base_product=base).update(atc_code=atc, dosage_form=form)

    create('tylolhot', respiratory, atc='R05X', form='powder')
    create('oseflu', None, atc='J05AH02', form='capsule')
    create('nasal-spray', respiratory, atc='R01AA07', form='spray')
    create('asist', respiratory, atc='R05CB01', form='other')
    create('ibuprofen-gel', painkillers, atc='M02AA13', form='gel')
    create('diclofenac-tab', painkillers, atc='M01AB05', form='tablet')
    create('katarin-pediatrik', respiratory, name='KATARIN PEDIATRIK SURUP', atc='R05X', form='syrup')
    create('foreign-cold', other_root, atc='R05X', form='tablet')
    return {'root': root, 'respiratory': respiratory, 'painkillers': painkillers}


@pytest.mark.django_db
def test_category_detail_accepts_slug_instead_of_failing_with_500(medicines):
    CategoryTranslation.objects.create(
        category=medicines['root'], locale='ru', name='Медикаменты',
        h1='Лекарства из Турции', meta_title='Лекарства из Турции | Mudaroba',
        meta_description='Оригинальные препараты из турецких аптек.', seo_text='Абзац.\n\nЕщё абзац.',
    )
    client = APIClient()

    response = client.get('/api/catalog/categories/medicines')
    assert response.status_code == 200
    assert response.json()['slug'] == 'medicines'
    assert response.json()['seo'] == [{
        'locale': 'ru',
        'h1': 'Лекарства из Турции',
        'meta_title': 'Лекарства из Турции | Mudaroba',
        'meta_description': 'Оригинальные препараты из турецких аптек.',
        'seo_text': 'Абзац.\n\nЕщё абзац.',
    }]

    # Подкатегория — и по slug, и по id (список по умолчанию отдаёт только корни).
    assert client.get('/api/catalog/categories/painkillers').status_code == 200
    assert client.get(f"/api/catalog/categories/{medicines['painkillers'].id}").status_code == 200
    assert client.get('/api/catalog/categories/no-such-category').status_code == 404


@pytest.mark.django_db
def test_category_list_returns_landing_seo_only_on_request(medicines):
    CategoryTranslation.objects.create(category=medicines['painkillers'], locale='en', name='Pain', h1='Turkish painkillers')
    client = APIClient()
    params = {'slug': 'painkillers', 'include_children': 'false'}

    plain = client.get('/api/catalog/categories', params).json()['results'][0]
    with_seo = client.get('/api/catalog/categories', {**params, 'include_seo': 'true'}).json()['results'][0]

    assert 'seo' not in plain
    assert with_seo['seo'][0]['h1'] == 'Turkish painkillers'


@pytest.mark.django_db
def test_collection_rule_matches_atc_keywords_and_forms_inside_parent_tree(medicines):
    root = medicines['root']
    CategoryCollection.objects.create(parent=root, name='От простуды', slug='ot-prostudy', atc_prefixes='R05X, j05ah')
    CategoryCollection.objects.create(parent=root, name='Мази', slug='mazi', dosage_forms='ointment,cream,gel')
    CategoryCollection.objects.create(parent=root, name='Детские', slug='detskie', name_keywords='pediatrik')
    CategoryCollection.objects.create(
        parent=medicines['respiratory'], name='Насморк', slug='ot-nasmorka', atc_prefixes='R01',
    )
    CategoryCollection.objects.create(
        parent=root, name='Простуда без противовирусных', slug='cold-only', atc_prefixes='R05X, J05AH',
        dosage_forms='powder,syrup,capsule', exclude_atc_prefixes='J05',
    )

    # Код АТХ без учёта регистра префикса; товар без категории виден в корневой подборке;
    # товар из чужого дерева категорий — нет.
    assert _medicine_slugs(collection='ot-prostudy') == {'tylolhot', 'oseflu', 'katarin-pediatrik'}
    assert _medicine_slugs(collection='mazi') == {'ibuprofen-gel'}
    assert _medicine_slugs(collection='detskie') == {'katarin-pediatrik'}
    assert _medicine_slugs(collection='ot-nasmorka') == {'nasal-spray'}
    assert _medicine_slugs(collection='cold-only') == {'tylolhot', 'katarin-pediatrik'}
    # Подборка сужает выборку и вместе с категорией страницы.
    assert _medicine_slugs(collection='ot-prostudy', category_slug='respiratory-ent') == {'tylolhot', 'katarin-pediatrik'}


@pytest.mark.django_db
def test_unknown_or_inactive_collection_returns_no_products(medicines):
    CategoryCollection.objects.create(parent=medicines['root'], name='Скрытая', slug='hidden', atc_prefixes='R05X', is_active=False)

    assert _medicine_slugs(collection='no-such-collection') == set()
    assert _medicine_slugs(collection='hidden') == set()


@pytest.mark.django_db
def test_collections_api_lists_by_parent_or_tree_and_returns_seo_in_detail(medicines):
    cold = CategoryCollection.objects.create(parent=medicines['root'], name='От простуды', slug='ot-prostudy', atc_prefixes='R05X', sort_order=1)
    CategoryCollection.objects.create(parent=medicines['respiratory'], name='Насморк', slug='ot-nasmorka', atc_prefixes='R01', sort_order=2)
    CategoryCollectionTranslation.objects.create(
        collection=cold, locale='ru', name='От простуды и гриппа', h1='Турецкие средства от простуды и гриппа',
        meta_title='От простуды | Mudaroba', meta_description='Описание.', seo_text='Текст.',
    )
    client = APIClient()

    tree = client.get('/api/catalog/collections', {'root_slug': 'medicines'}).json()['results']
    direct = client.get('/api/catalog/collections', {'parent_slug': 'respiratory-ent'}).json()['results']
    detail = client.get('/api/catalog/collections/ot-prostudy').json()

    assert [row['slug'] for row in tree] == ['ot-prostudy', 'ot-nasmorka']
    assert tree[0]['translations'] == [{'locale': 'ru', 'name': 'От простуды и гриппа'}]
    assert [(row['slug'], row['parent_slug']) for row in direct] == [('ot-nasmorka', 'respiratory-ent')]
    assert detail['parent_slug'] == 'medicines'
    assert detail['translations'][0]['h1'] == 'Турецкие средства от простуды и гриппа'
    assert detail['translations'][0]['seo_text'] == 'Текст.'
    assert client.get('/api/catalog/collections/no-such').status_code == 404


@pytest.mark.django_db
def test_sitemap_lists_only_collections_with_products(medicines):
    CategoryCollection.objects.create(parent=medicines['respiratory'], name='Насморк', slug='ot-nasmorka', atc_prefixes='R01')
    CategoryCollection.objects.create(parent=medicines['root'], name='Свечи', slug='svechi', dosage_forms='suppository')

    response = APIClient().get('/api/catalog/sitemap-entries', {'kind': 'collections'})

    assert response.status_code == 200
    rows = response.json()['results']
    assert [(row['slug'], row['parent_slug']) for row in rows] == [('ot-nasmorka', 'respiratory-ent')]
    assert response.json()['count'] == 1


@pytest.mark.django_db
def test_collection_rule_validation(medicines):
    with pytest.raises(ValidationError):
        CategoryCollection(parent=medicines['root'], name='Пустая', slug='empty').full_clean()
    with pytest.raises(ValidationError):
        CategoryCollection(parent=medicines['root'], name='Пасты', slug='pasty', dosage_forms='paste').full_clean()
    CategoryCollection(parent=medicines['root'], name='Спреи', slug='spreyi', dosage_forms='spray').full_clean()


@pytest.mark.django_db
def test_landing_seo_data_migration_fills_only_empty_fields_and_is_repeatable(medicines):
    from importlib import import_module

    from django.apps import apps

    migration = import_module('apps.catalog.migrations.0222_medicine_landing_seo_texts')
    CategoryTranslation.objects.create(category=medicines['painkillers'], locale='ru', name='Обезболивающие', h1='Своё H1 из админки')
    CategoryCollection.objects.create(parent=medicines['root'], name='Уже есть', slug='spreyi', dosage_forms='spray')

    migration.fill_landing_seo(apps, None)
    migration.fill_landing_seo(apps, None)

    root_ru = CategoryTranslation.objects.get(category=medicines['root'], locale='ru')
    root_en = CategoryTranslation.objects.get(category=medicines['root'], locale='en')
    painkillers_ru = CategoryTranslation.objects.get(category=medicines['painkillers'], locale='ru')
    assert root_ru.name == 'Медикаменты' and root_ru.h1 == 'Лекарства из Турции'
    assert root_en.h1 == 'Medicines from Turkey' and root_en.seo_text
    assert painkillers_ru.h1 == 'Своё H1 из админки'
    assert painkillers_ru.meta_title and painkillers_ru.seo_text

    # Подборки созданы только у существующих родителей, существующая не тронута
    created = dict(CategoryCollection.objects.values_list('slug', 'parent__slug'))
    assert created['ot-prostudy-i-grippa'] == 'medicines'
    assert created['ot-nasmorka'] == 'respiratory-ent'
    assert 'varikoz' not in created  # нет категории cardio в тестовой базе
    assert CategoryCollection.objects.get(slug='spreyi').name == 'Уже есть'
    cold = CategoryCollection.objects.get(slug='ot-prostudy-i-grippa')
    assert cold.translations.count() == 2
    assert _medicine_slugs(collection='ot-prostudy-i-grippa') == {'tylolhot', 'oseflu', 'katarin-pediatrik'}
