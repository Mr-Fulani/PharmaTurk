import test from 'node:test'
import assert from 'node:assert/strict'

import {
  createPromiseTtlCache,
  createStaleWhileRevalidateCache,
  settleWithin,
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

test('settleWithin returns the value when it arrives in time', async () => {
  assert.deepEqual(await settleWithin(Promise.resolve(['brand']), 50, []), ['brand'])
})

test('settleWithin falls back on timeout without cancelling the work', async () => {
  let resolveSlow
  const slow = new Promise((resolve) => {
    resolveSlow = resolve
  })
  assert.deepEqual(await settleWithin(slow, 5, []), [])
  resolveSlow(['late'])
  assert.deepEqual(await slow, ['late'])
})

test('stale-while-revalidate cache serves stale value and refreshes once in background', async () => {
  let clock = 0
  let calls = 0
  let resolveRefresh
  const cache = createStaleWhileRevalidateCache({ freshMs: 100, now: () => clock })
  const loader = () => {
    calls += 1
    if (calls === 1) return 'v1'
    return new Promise((resolve) => {
      resolveRefresh = resolve
    })
  }

  assert.equal(await cache.get('section', loader), 'v1')
  clock = 150
  assert.equal(await cache.get('section', loader), 'v1')
  assert.equal(await cache.get('section', loader), 'v1')
  assert.equal(calls, 2)
  resolveRefresh('v2')
  await new Promise((resolve) => setImmediate(resolve))
  assert.equal(await cache.get('section', loader), 'v2')
})

test('stale-while-revalidate cache does not store rejected values', async () => {
  const cache = createStaleWhileRevalidateCache({ freshMs: 100, shouldStore: (value) => value !== '' })
  let calls = 0
  const loader = () => {
    calls += 1
    return calls === 1 ? '' : 'xml'
  }
  assert.equal(await cache.get('section', loader), '')
  assert.equal(await cache.get('section', loader), 'xml')
  assert.equal(calls, 2)
})
