import test from 'node:test'
import assert from 'node:assert/strict'

import { formatAddressLine, splitFullName } from './checkoutContact.js'

test('full name from a saved address is split into first and last name', () => {
  assert.deepEqual(splitFullName('  Иван   Петров '), { firstName: 'Иван', lastName: 'Петров' })
  assert.deepEqual(splitFullName('Анна Мария Санчес'), { firstName: 'Анна', lastName: 'Мария Санчес' })
})

test('name without a last name leaves the last name empty so the buyer fills it in', () => {
  assert.deepEqual(splitFullName('Иван'), { firstName: 'Иван', lastName: '' })
  assert.deepEqual(splitFullName(undefined), { firstName: '', lastName: '' })
})

test('address line keeps everything the buyer entered, including the postal code', () => {
  assert.equal(
    formatAddressLine({
      country: 'Россия', region: 'Московская обл.', postal_code: '101000', city: 'Москва',
      street: 'Тверская', house: '1', apartment: '5', entrance: '2', floor: '3', intercom: '5К',
    }),
    'Россия, Московская обл., 101000, Москва, Тверская 1, кв. 5, подъезд 2, этаж 3, домофон 5К',
  )
})

test('address line skips empty parts', () => {
  assert.equal(
    formatAddressLine({ country: 'Турция', city: 'Стамбул', street: 'İstiklal', house: '10', apartment: '' }),
    'Турция, Стамбул, İstiklal 10',
  )
  assert.equal(formatAddressLine(null), '')
})
