import test from 'node:test'
import assert from 'node:assert/strict'

import { buildMaxShareText, buildMaxShareUrl } from './shareHelpers.js'

test('buildMaxShareText combines title and url', () => {
  assert.equal(
    buildMaxShareText('https://mudaroba.com/about-us', 'About Us'),
    'About Us\nhttps://mudaroba.com/about-us'
  )
})

test('buildMaxShareText falls back to url when title is empty', () => {
  assert.equal(
    buildMaxShareText('https://mudaroba.com/about-us', ''),
    'https://mudaroba.com/about-us'
  )
})

test('buildMaxShareUrl encodes multiline text for MAX deeplink', () => {
  assert.equal(
    buildMaxShareUrl('https://mudaroba.com/about-us', 'About Us'),
    'https://max.ru/:share?text=About%20Us%0Ahttps%3A%2F%2Fmudaroba.com%2Fabout-us'
  )
})
