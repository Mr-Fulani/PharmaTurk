import assert from 'node:assert/strict'
import test from 'node:test'

import { buildFavoriteProductHref } from './favoriteLinks.js'

test('favorite variant link restores the exact selected variant', () => {
  assert.equal(
    buildFavoriteProductHref('/product/perfumery/base-product', 'variant 50/ml'),
    '/product/perfumery/base-product?active_variant_slug=variant%2050%2Fml'
  )
})

test('favorite link stays unchanged for products without a saved variant', () => {
  assert.equal(
    buildFavoriteProductHref('/product/uslugi/service', null),
    '/product/uslugi/service'
  )
})
