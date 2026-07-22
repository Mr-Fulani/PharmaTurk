import assert from 'node:assert/strict'
import test from 'node:test'

import { deduplicateFeaturedProducts } from './featuredProducts.js'

test('deduplicates a canonical Product and its linked domain row', () => {
  const canonical = { id: 7122, slug: 'silver-ring', product_type: 'jewelry' }
  const domain = { id: 2, base_product_id: 7122, slug: 'silver-ring', product_type: 'jewelry' }

  assert.deepEqual(deduplicateFeaturedProducts([canonical, domain]), [canonical])
  assert.deepEqual(deduplicateFeaturedProducts([domain, canonical]), [domain])
})

test('uses base_product_id when linked rows have different legacy slugs', () => {
  const canonical = { id: 100, slug: 'legacy-slug-2', product_type: 'clothing' }
  const domain = { id: 4, base_product_id: 100, slug: 'legacy-slug', product_type: 'clothing' }

  assert.equal(deduplicateFeaturedProducts([canonical, domain]).length, 1)
})

test('keeps products with the same name but different public slugs', () => {
  const products = [
    { id: 1, name: 'FRIHETEN', slug: 'friheten-59326624', product_type: 'furniture' },
    { id: 2, name: 'FRIHETEN', slug: 'friheten-69444330', product_type: 'furniture' },
  ]

  assert.deepEqual(deduplicateFeaturedProducts(products), products)
})

test('keeps equal slugs from different product types', () => {
  const products = [
    { id: 1, slug: 'classic', product_type: 'books' },
    { id: 1, slug: 'classic', product_type: 'jewelry' },
  ]

  assert.deepEqual(deduplicateFeaturedProducts(products), products)
})
