import assert from 'node:assert/strict'
import test from 'node:test'

import {
  favoriteApiProductId,
  matchesFavoriteProductIdentity,
} from './favoriteIdentity.js'

test('favorites use public base_product_id instead of a colliding domain id', () => {
  assert.equal(favoriteApiProductId({ id: 4, base_product_id: 70 }), 70)
})

test('favorites keep the card id when no public product link exists', () => {
  assert.equal(favoriteApiProductId({ id: 41 }), 41)
})

test('refreshed favorite matches a card by returned public base id', () => {
  assert.equal(
    matchesFavoriteProductIdentity(
      { id: 4, base_product_id: 70, slug: 'selected-product' },
      70,
      'selected-product'
    ),
    true
  )
})

test('refreshed favorite still matches by slug when serializers expose different ids', () => {
  assert.equal(
    matchesFavoriteProductIdentity(
      { id: 9, base_product_id: 70, slug: 'selected-product' },
      71,
      'selected-product'
    ),
    true
  )
  assert.equal(
    matchesFavoriteProductIdentity(
      { id: 9, base_product_id: 70, slug: 'other-product' },
      71,
      'selected-product'
    ),
    false
  )
})
