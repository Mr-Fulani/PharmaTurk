import assert from 'node:assert/strict'
import test from 'node:test'

import {
  canPublishSchemaOffer,
  shouldPublishProductSchema,
  resolveSchemaAvailability,
  resolveSchemaSku,
  sourceRefreshBlocksPurchase,
  sourceRefreshNeedsManagerPrice,
  SCHEMA_RETURN_POLICY,
  SCHEMA_SHIPPING_COUNTRIES,
  buildSchemaImages,
  isOwnDomainImage,
  pickOwnDomainImage,
  preferOwnDomainImages,
  buildSchemaShippingDetails,
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

test('shipping details: 5 $ in the offer currency, 7–14 days, owner countries', () => {
  const details = buildSchemaShippingDetails({ RUB: '402.50', USD: '5.00' }, 'rub')
  assert.deepEqual(details.shippingRate, { '@type': 'MonetaryAmount', value: 402.5, currency: 'RUB' })
  const { handlingTime, transitTime } = details.deliveryTime
  assert.equal(handlingTime.minValue + transitTime.minValue, 7)
  assert.equal(handlingTime.maxValue + transitTime.maxValue, 14)
  const countries = details.shippingDestination.map((region) => region.addressCountry)
  for (const code of ['KZ', 'UZ', 'AZ', 'DE', 'TR', 'AE', 'US', 'FR']) assert.ok(countries.includes(code), code)
  assert.ok(!countries.includes('RU'))
})

test('no shipping details without a rate in the offer currency (furniture, missing rate)', () => {
  assert.equal(buildSchemaShippingDetails(null, 'USD'), undefined)
  assert.equal(buildSchemaShippingDetails({ USD: '5.00' }, 'KZT'), undefined)
})

test('return policy covers every shipping country', () => {
  for (const code of SCHEMA_SHIPPING_COUNTRIES) assert.ok(SCHEMA_RETURN_POLICY.applicableCountry.includes(code), code)
})

test('schema images: main first, unique, at most 10', () => {
  assert.deepEqual(buildSchemaImages(['a', 'b', 'a', '', null, 'c']), ['a', 'b', 'c'])
  assert.equal(buildSchemaImages(Array.from({ length: 15 }, (_, i) => `img${i}`)).length, 10)
})

test('картинки разметки: чужой CDN убирается, если есть свои копии; своих нет — список как есть', () => {
  const site = 'https://mudaroba.com'
  const cdn = 'https://img-lcwaikiki.mncdn.com/pim/a.jpg'
  const own1 = 'https://mudaroba.com/api/catalog/proxy-media/?path=products%2Fa.jpg'
  const own2 = 'https://cdn.mudaroba.com/products/b.jpg'
  assert.equal(isOwnDomainImage(own1, site), true)
  assert.equal(isOwnDomainImage(own2, site), true)
  assert.equal(isOwnDomainImage(cdn, site), false)
  assert.equal(isOwnDomainImage('https://evilmudaroba.com/x.jpg', site), false)
  assert.equal(isOwnDomainImage('not a url', site), false)
  assert.deepEqual(preferOwnDomainImages([cdn, own1, own2], site), [own1, own2])
  assert.deepEqual(preferOwnDomainImages([cdn], site), [cdn])
  // Главное фото своё, галерея ещё на чужом CDN — ракурсы не теряются, своё первым
  const cdn2 = 'https://img-lcwaikiki.mncdn.com/pim/b.jpg'
  assert.deepEqual(preferOwnDomainImages([own1, cdn, cdn2], site), [own1, cdn, cdn2])
  assert.deepEqual(preferOwnDomainImages([cdn, own1, cdn2], site), [own1, cdn, cdn2])
  assert.equal(pickOwnDomainImage(cdn, [own1, own2], site), own1)
  const gif = 'https://mudaroba.com/api/catalog/proxy-media/?path=products%2Fmain-g.gif'
  assert.equal(pickOwnDomainImage(cdn, [gif, own2], site), own2)
  assert.equal(pickOwnDomainImage(cdn, [], site), cdn)
  assert.equal(pickOwnDomainImage(own2, [own1], site), own2)
})
