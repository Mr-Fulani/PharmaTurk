import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildCatalogSeoState,
  isCatalogPageOutOfRange,
  isCategoryInProductTree,
  selectExactCategory,
} from './categoryRouting.js'

test('eyewear remains in accessories and is not treated as shoes', () => {
  const category = {
    categoryType: 'accessories',
    inferredType: 'eyewear',
    routeSlug: 'eyewear',
    ancestors: [{ slug: 'accessories' }],
  }

  assert.equal(isCategoryInProductTree(category, 'shoes'), false)
})

test('legacy shoe subcategory is recognized through its ancestor', () => {
  const category = {
    categoryType: null,
    inferredType: 'sneakers',
    routeSlug: 'sneakers',
    ancestors: [{ slug: 'shoes' }],
  }

  assert.equal(isCategoryInProductTree(category, 'shoes'), true)
})

test('nested furniture category is recognized through its category type', () => {
  assert.equal(
    isCategoryInProductTree(
      { categoryType: 'furniture', inferredType: 'tables', routeSlug: 'tables', ancestors: [] },
      'furniture'
    ),
    true
  )
})

test('exact category is selected even when descendants are returned first', () => {
  const categories = [
    { slug: 'mens-sunglasses', gender: 'men' },
    { slug: 'sunglasses' },
    { slug: 'eyewear', category_type_slug: 'accessories' },
  ]

  assert.deepEqual(selectExactCategory(categories, 'eyewear'), categories[2])
})

test('gendered categories from other product trees are never classified as shoes', () => {
  const categories = [
    ['mens-sunglasses', 'accessories', ['accessories', 'eyewear', 'sunglasses']],
    ['kids-beds', 'furniture', ['furniture', 'kids-furniture']],
    ['mens-fragrances', 'perfumery', ['perfumery', 'fragrances']],
    ['uw-mens-underwear', 'underwear', ['underwear']],
    ['hw-children-headwear', 'headwear', ['headwear']],
    ['kids-supplements', 'supplements', ['supplements']],
    ['children-wheelchairs', 'medical-equipment', ['medical-equipment', 'rehabilitation-equipment']],
    ['mens-jewelry', 'jewelry', ['jewelry']],
    ['islamic-outerwear-women', 'islamic-clothing', ['islamic-clothing']],
    ['svc-children-furniture', 'uslugi', ['uslugi', 'svc-furniture-appliance']],
    ['body-parts', 'auto-parts', ['auto-parts']],
  ]

  for (const [routeSlug, categoryType, ancestorSlugs] of categories) {
    const context = {
      categoryType,
      inferredType: categoryType,
      routeSlug,
      ancestors: ancestorSlugs.map((slug) => ({ slug })),
    }
    assert.equal(isCategoryInProductTree(context, 'shoes'), false, routeSlug)
  }
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
