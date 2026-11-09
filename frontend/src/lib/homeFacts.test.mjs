import test from 'node:test'
import assert from 'node:assert/strict'

import { countBrandsWithProducts, countCatalogProducts, formatCount, roundDownToHundreds, roundDownToThousands } from './homeFacts.js'

test('товары считаются по корневым категориям без услуг', () => {
  const categories = [
    { slug: 'medicines', products_count: 12274 },
    { slug: 'clothing', products_count: 2054 },
    { slug: 'uslugi', products_count: 16 },
    { slug: 'electronics', products_count: 0 },
    { slug: 'broken', products_count: null },
  ]
  assert.equal(countCatalogProducts(categories), 14328)
  assert.equal(countCatalogProducts(undefined), 0)
})

test('бренды без товаров не считаются; ответ API — список или страница', () => {
  const list = [{ products_count: 3 }, { products_count: 0 }, {}, { products_count: 1 }]
  assert.equal(countBrandsWithProducts(list), 2)
  assert.equal(countBrandsWithProducts({ results: list }), 2)
  assert.equal(countBrandsWithProducts(null), 0)
})

test('округление вниз до тысяч, меньше тысячи — без числа', () => {
  assert.equal(roundDownToThousands(27511), 27000)
  assert.equal(roundDownToThousands(1000), 1000)
  assert.equal(roundDownToThousands(999), 0)
  assert.equal(roundDownToThousands('abc'), 0)
})

test('разделитель разрядов по языку', () => {
  assert.equal(formatCount(27000, 'ru'), '27 000')
  assert.equal(formatCount(27000, 'en'), '27,000')
  assert.equal(formatCount(883, 'ru'), '883')
})

test('бренды для мета-описания — вниз до сотен', () => {
  assert.equal(roundDownToHundreds(883), 800)
  assert.equal(roundDownToHundreds(100), 100)
  assert.equal(roundDownToHundreds(99), 0)
  assert.equal(roundDownToHundreds(undefined), 0)
})
