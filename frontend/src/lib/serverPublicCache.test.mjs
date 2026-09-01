import test from 'node:test'
import assert from 'node:assert/strict'

import {
  createPromiseTtlCache,
  stablePublicCacheKey,
} from './serverPublicCache.js'

test('server public cache deduplicates concurrent loaders', async () => {
  const cache = createPromiseTtlCache()
  let calls = 0
  let resolveLoader
  const loader = () => {
    calls += 1
    return new Promise((resolve) => {
      resolveLoader = resolve
    })
  }

  const first = cache.get('categories:ru', loader)
  const second = cache.get('categories:ru', loader)
  await Promise.resolve()
  assert.equal(calls, 1)
  resolveLoader(['medicines'])
  assert.deepEqual(await first, ['medicines'])
  assert.deepEqual(await second, ['medicines'])
})

test('server public cache expires values and never caches failures', async () => {
  let timestamp = 100
  const cache = createPromiseTtlCache({ now: () => timestamp })
  let calls = 0
  const loader = async () => ++calls

  assert.equal(await cache.get('brands', loader, 50), 1)
  timestamp = 149
  assert.equal(await cache.get('brands', loader, 50), 1)
  timestamp = 150
  assert.equal(await cache.get('brands', loader, 50), 2)

  await assert.rejects(cache.get('failure', async () => {
    throw new Error('temporary')
  }))
  assert.equal(await cache.get('failure', async () => 'recovered'), 'recovered')
})

test('server public cache keys are stable across object key order', () => {
  assert.equal(
    stablePublicCacheKey('catalog', { lang: 'ru', params: { slug: 'medicines', all: true } }),
    stablePublicCacheKey('catalog', { params: { all: true, slug: 'medicines' }, lang: 'ru' })
  )
})
