import assert from 'node:assert/strict'
import test from 'node:test'

import { canPublishSchemaOffer, resolveSchemaAvailability } from './productAvailability.js'

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
