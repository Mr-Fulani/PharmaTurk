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
