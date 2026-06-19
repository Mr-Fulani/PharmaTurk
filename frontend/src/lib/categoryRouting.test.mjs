import test from 'node:test'
import assert from 'node:assert/strict'

import { isCategoryInProductTree, selectExactCategory } from './categoryRouting.js'

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
