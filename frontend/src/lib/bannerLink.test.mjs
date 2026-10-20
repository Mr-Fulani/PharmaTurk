import assert from 'node:assert/strict'
import test from 'node:test'

import { resolveBannerLink } from './bannerLink.js'

const hosts = ['mudaroba.com', 'localhost']

test('own absolute URLs become locale-neutral internal paths', () => {
  assert.deepEqual(resolveBannerLink('https://mudaroba.com/categories/medicines', hosts), { internal: '/categories/medicines' })
  assert.deepEqual(resolveBannerLink('https://www.mudaroba.com/how-to-order-medicines#sourcing', hosts), { internal: '/how-to-order-medicines#sourcing' })
  assert.deepEqual(resolveBannerLink('https://mudaroba.com/en/brand/lc-waikiki?x=1', hosts), { internal: '/brand/lc-waikiki?x=1' })
  assert.deepEqual(resolveBannerLink('https://mudaroba.com/ru', hosts), { internal: '/' })
  assert.deepEqual(resolveBannerLink('https://mudaroba.com', hosts), { internal: '/' })
})

test('relative paths stay internal, other domains stay external', () => {
  assert.deepEqual(resolveBannerLink('/delivery', hosts), { internal: '/delivery' })
  assert.deepEqual(resolveBannerLink('https://instagram.com/mudaroba', hosts), { external: 'https://instagram.com/mudaroba' })
  assert.deepEqual(resolveBannerLink('https://mudaroba.com.evil.io/x', hosts), { external: 'https://mudaroba.com.evil.io/x' })
  // /english — не префикс локали
  assert.deepEqual(resolveBannerLink('https://mudaroba.com/english-books', hosts), { internal: '/english-books' })
})
