import assert from 'node:assert/strict'
import test from 'node:test'
import { isSoldOutCartError } from './cartStock.js'

const error = (status, data) => ({ response: { status, data } })

test('закончился у поставщика: 400 и available 0', () => {
  assert.equal(isSoldOutCartError(error(400, { detail: 'Недостаточно товара в наличии', available: 0 })), true)
})

test('остаток есть, но меньше запрошенного — не «нет в наличии»', () => {
  assert.equal(isSoldOutCartError(error(400, { detail: 'Недостаточно товара в наличии', available: 2 })), false)
})

test('другие ошибки не путаем с отсутствием товара', () => {
  assert.equal(isSoldOutCartError(error(400, { detail: 'Укажите размер' })), false)
  assert.equal(isSoldOutCartError(error(409, { code: 'source_out_of_stock', available: 0 })), false)
  assert.equal(isSoldOutCartError(error(400, { code: 'source_out_of_stock', available: 0 })), false)
  assert.equal(isSoldOutCartError(error(500, { available: 0 })), false)
  assert.equal(isSoldOutCartError(new Error('Network Error')), false)
  assert.equal(isSoldOutCartError(undefined), false)
})
