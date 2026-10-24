import test from 'node:test'
import assert from 'node:assert/strict'

import { formatRestrictedCountries } from './importRestriction.js'

const t = (_key, fallback) => fallback

test('restricted countries are named in a fixed order', () => {
  assert.equal(formatRestrictedCountries(['UZ', 'KZ', 'RU'], t), 'Россию, Казахстан и Узбекистан')
  assert.equal(formatRestrictedCountries(['KZ', 'RU'], t), 'Россию и Казахстан')
  assert.equal(formatRestrictedCountries(['RU'], t), 'Россию')
})

test('no restriction gives an empty string', () => {
  assert.equal(formatRestrictedCountries([], t), '')
  assert.equal(formatRestrictedCountries(null, t), '')
  assert.equal(formatRestrictedCountries(undefined, t), '')
})
