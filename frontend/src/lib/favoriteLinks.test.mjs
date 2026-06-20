import assert from 'node:assert/strict'
import test from 'node:test'

import { buildFavoriteProductHref, matchesFavoriteSlug } from './favoriteLinks.js'

test('favorite variant link restores the exact selected variant', () => {
  assert.equal(
    buildFavoriteProductHref('/product/shoes/base-product', 'red variant', '42'),
    '/product/shoes/base-product?active_variant_slug=red+variant&favorite_size=42'
  )
})

test('favorite link stays unchanged for products without a saved variant', () => {
  assert.equal(
    buildFavoriteProductHref('/product/uslugi/service', null),
    '/product/uslugi/service'
  )
})

test('service favorite matches its regular product slug', () => {
  assert.equal(matchesFavoriteSlug(null, 'service-slug', 'service-slug'), true)
})

test('variant favorite always prefers the exact saved variant slug', () => {
  assert.equal(matchesFavoriteSlug('variant-red', 'base-product', 'variant-red'), true)
  assert.equal(matchesFavoriteSlug('variant-red', 'base-product', 'base-product'), false)
})
