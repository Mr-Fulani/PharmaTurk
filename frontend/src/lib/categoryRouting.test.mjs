import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildCatalogSeoState,
  buildCategoryLandingLinkGroups,
  isCatalogPageOutOfRange,
  selectExactCategory,
} from './categoryRouting.js'

test('exact category is selected even when descendants are returned first', () => {
  const categories = [
    { slug: 'mens-sunglasses', gender: 'men' },
    { slug: 'sunglasses' },
    { slug: 'eyewear', category_type_slug: 'accessories' },
  ]

  assert.deepEqual(selectExactCategory(categories, 'eyewear'), categories[2])
})

test('catalog pagination keeps the first empty page but rejects pages after the end', () => {
  assert.equal(isCatalogPageOutOfRange('1', 0, 12), false)
  assert.equal(isCatalogPageOutOfRange('2', 0, 12), true)
  assert.equal(isCatalogPageOutOfRange('345', 4135, 12), false)
  assert.equal(isCatalogPageOutOfRange('346', 4135, 12), true)
})

test('catalog pagination rejects malformed, fractional and non-positive pages', () => {
  assert.equal(isCatalogPageOutOfRange('not-a-number', 50, 12), true)
  assert.equal(isCatalogPageOutOfRange('1.5', 50, 12), true)
  assert.equal(isCatalogPageOutOfRange('0', 50, 12), true)
  assert.equal(isCatalogPageOutOfRange('-1', 50, 12), true)
})

test('plain catalog pagination is self-canonical and links adjacent pages', () => {
  assert.deepEqual(
    buildCatalogSeoState('/categories/medicines', { slug: 'medicines', page: '2' }, 2, 4),
    {
      canonicalPath: '/categories/medicines?page=2',
      hasFilters: false,
      noindex: false,
      previousPath: '/categories/medicines',
      nextPath: '/categories/medicines?page=3',
    }
  )
})

test('catalog filters are noindex and canonicalize to the clean category', () => {
  assert.deepEqual(
    buildCatalogSeoState(
      '/categories/medicines',
      { slug: 'medicines', page: '3', brand_id: ['12'], ordering: 'price_asc' },
      3,
      9
    ),
    {
      canonicalPath: '/categories/medicines',
      hasFilters: true,
      noindex: true,
      previousPath: null,
      nextPath: null,
    }
  )
})

test('collection route param is not a filter: collection page is indexable and self-canonical', () => {
  assert.deepEqual(
    buildCatalogSeoState(
      '/categories/medicines/ot-prostudy-i-grippa',
      { slug: 'medicines', collection: 'ot-prostudy-i-grippa', page: '2' },
      2,
      3,
      30
    ),
    {
      canonicalPath: '/categories/medicines/ot-prostudy-i-grippa?page=2',
      hasFilters: false,
      noindex: false,
      previousPath: '/categories/medicines/ot-prostudy-i-grippa',
      nextPath: '/categories/medicines/ot-prostudy-i-grippa?page=3',
    }
  )
})

test('empty optional catalog filters do not create a noindex page', () => {
  const state = buildCatalogSeoState(
    '/categories/books',
    { slug: 'books', brand_id: '', search: undefined },
    1,
    1
  )

  assert.equal(state.noindex, false)
  assert.equal(state.canonicalPath, '/categories/books')
})

test('empty category (no products) is noindex but stays canonical to itself', () => {
  assert.deepEqual(
    buildCatalogSeoState('/categories/flashlights', { slug: 'flashlights' }, 1, 1, 0),
    {
      canonicalPath: '/categories/flashlights',
      hasFilters: false,
      noindex: true,
      previousPath: null,
      nextPath: null,
    }
  )
})

test('category with products stays indexable when count is passed', () => {
  assert.equal(buildCatalogSeoState('/categories/medicines', { slug: 'medicines' }, 1, 3, 30).noindex, false)
})

test('landing block links sections of any category, without empty ones', () => {
  const groups = buildCategoryLandingLinkGroups({
    sections: [
      { href: '/categories/sneakers', label: 'Кроссовки', productsCount: 378 },
      { href: '/categories/boots', label: 'Ботинки', productsCount: 0 },
      { href: '/categories/sandals', label: 'Сандалии' },
    ],
    collections: [],
    isCollectionPage: false,
    sectionsTitle: 'Разделы',
    collectionsTitle: 'Подборки',
  })

  assert.deepEqual(groups, [{
    title: 'Разделы',
    links: [
      { href: '/categories/sneakers', label: 'Кроссовки' },
      { href: '/categories/sandals', label: 'Сандалии' },
    ],
  }])
})

test('collection page links only collections', () => {
  const groups = buildCategoryLandingLinkGroups({
    sections: [{ href: '/categories/cardio', label: 'Сердце', productsCount: 5 }],
    collections: [{ href: '/categories/medicines/kapli', label: 'Капли' }],
    isCollectionPage: true,
    sectionsTitle: 'Разделы',
    collectionsTitle: 'Подборки',
  })

  assert.deepEqual(groups, [{ title: 'Подборки', links: [{ href: '/categories/medicines/kapli', label: 'Капли' }] }])
})
