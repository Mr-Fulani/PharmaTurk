import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildSimilarFallbackParams,
  getSimilarFallbackEndpoint,
  sameSimilarProductType,
} from './similarProducts.js'

test('supplement fallback uses the dedicated supplement catalogue', () => {
  assert.equal(
    getSimilarFallbackEndpoint('supplements'),
    '/catalog/supplements/products',
  )
})

test('fallback request preserves product type and exact category', () => {
  assert.deepEqual(
    buildSimilarFallbackParams({ productType: 'supplements', categoryId: 24170, limit: 8 }),
    {
      limit: 9,
      ordering: '-created_at',
      view: 'card',
      product_type: 'supplements',
      category_id: 24170,
    },
  )
})

test('unrelated product types are rejected from client fallback results', () => {
  assert.equal(sameSimilarProductType('supplements', 'supplements'), true)
  assert.equal(sameSimilarProductType('clothing', 'supplements'), false)
})
