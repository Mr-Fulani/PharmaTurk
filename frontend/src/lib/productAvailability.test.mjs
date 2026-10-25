import assert from 'node:assert/strict'
import test from 'node:test'

import {
  canPublishSchemaOffer,
  shouldPublishProductSchema,
  resolveSchemaAvailability,
  resolveSchemaSku,
  sourceRefreshBlocksPurchase,
  sourceRefreshNeedsManagerPrice,
} from './productAvailability.js'

test('supplier-projected out of stock wins over stale variant availability', () => {
  assert.equal(
    resolveSchemaAvailability({
      availabilityStatus: 'out_of_stock',
      isAvailable: false,
      variantAvailable: true,
      variantStockQuantity: 5,
    }),
    'https://schema.org/OutOfStock',
  )
})

test('discontinued status is preserved in public Offer JSON-LD', () => {
  assert.equal(
    resolveSchemaAvailability({ availabilityStatus: 'discontinued' }),
    'https://schema.org/Discontinued',
  )
})

test('selected unavailable variant remains out of stock for an available product', () => {
  assert.equal(
    resolveSchemaAvailability({
      availabilityStatus: 'in_stock',
      isAvailable: true,
      variantAvailable: false,
    }),
    'https://schema.org/OutOfStock',
  )
})

test('available product defaults to InStock', () => {
  assert.equal(
    resolveSchemaAvailability({
      availabilityStatus: 'in_stock',
      isAvailable: true,
      variantAvailable: true,
    }),
    'https://schema.org/InStock',
  )
})

test('medicine never publishes Offer: site states it does not sell medicines', () => {
  assert.equal(
    canPublishSchemaOffer({ price: '526.68', isMedicine: true, isSupplement: false, canAddToCart: true }),
    false,
  )
})

test('supplement publishes Offer only when it can be added to cart', () => {
  assert.equal(canPublishSchemaOffer({ price: '10', isMedicine: false, isSupplement: true, canAddToCart: false }), false)
  assert.equal(canPublishSchemaOffer({ price: '10', isMedicine: false, isSupplement: true, canAddToCart: true }), true)
})

test('regular product publishes Offer only with a price', () => {
  assert.equal(canPublishSchemaOffer({ price: '10', isMedicine: false, isSupplement: false }), true)
  assert.equal(canPublishSchemaOffer({ price: null, isMedicine: false, isSupplement: false }), false)
})

test('schema sku keeps short slugs and replaces ones Google rejects', () => {
  assert.equal(resolveSchemaSku({ slug: 'beret-s-kozyrkom', productType: 'headwear', id: 7 }), 'beret-s-kozyrkom')
  const longSlug = 'cleocin-150-mg-16-kapsul-cleocin-150-mg-16-kapsul-2'
  assert.ok(longSlug.length > 50)
  assert.equal(resolveSchemaSku({ slug: longSlug, productType: 'medicines', id: 42 }), 'medicines-42')
})

test('paid source access refusal keeps purchase and asks manager for the price', () => {
  const refused = { status: 'failed', error_code: 'paid_access_unavailable' }
  assert.equal(sourceRefreshNeedsManagerPrice(refused), true)
  assert.equal(sourceRefreshBlocksPurchase(refused), false)
})

test('other card refresh failures still block purchase', () => {
  for (const errorCode of ['source_unavailable', 'source_not_found', 'rate_limited']) {
    const failed = { status: 'failed', error_code: errorCode }
    assert.equal(sourceRefreshBlocksPurchase(failed), true)
    assert.equal(sourceRefreshNeedsManagerPrice(failed), false)
  }
  assert.equal(sourceRefreshBlocksPurchase({ status: 'idle' }), false)
  assert.equal(sourceRefreshBlocksPurchase(null), false)
})

test('product schema without offer or rating is not published for Product and Drug', () => {
  assert.equal(shouldPublishProductSchema({ type: 'Drug', hasOffer: false, hasRating: false }), false)
  assert.equal(shouldPublishProductSchema({ type: 'Product', hasOffer: false, hasRating: false }), false)
  assert.equal(shouldPublishProductSchema({ type: 'Drug', hasOffer: false, hasRating: true }), true)
  assert.equal(shouldPublishProductSchema({ type: 'Product', hasOffer: true, hasRating: false }), true)
  // Book и Service — не сниппет товара Google: выводятся как раньше.
  assert.equal(shouldPublishProductSchema({ type: 'Book', hasOffer: false, hasRating: false }), true)
  assert.equal(shouldPublishProductSchema({ type: 'Service', hasOffer: false, hasRating: false }), true)
})
