import test from 'node:test'
import assert from 'node:assert/strict'

import { resolveRequestCurrency } from './requestCurrency.js'

test('explicit request currency wins over cookie and preferred currency', () => {
  // checkout отправляет заявку в той валюте, в которой показывал суммы клиенту
  assert.equal(resolveRequestCurrency({ explicit: 'RUB', stored: 'USD', preferred: 'USD' }), 'RUB')
})

test('cookie currency is used when request has no explicit currency', () => {
  assert.equal(resolveRequestCurrency({ explicit: undefined, stored: 'EUR', preferred: 'USD' }), 'EUR')
})

test('falls back to preferred currency, then RUB', () => {
  assert.equal(resolveRequestCurrency({ preferred: 'USD' }), 'USD')
  assert.equal(resolveRequestCurrency({}), 'RUB')
})
