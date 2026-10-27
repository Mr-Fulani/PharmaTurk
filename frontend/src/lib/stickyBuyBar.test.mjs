import assert from 'node:assert/strict'
import test from 'node:test'
import { isActionBlockOffscreen, stickyBuyBarMode } from './stickyBuyBar.js'

const base = { isService: false, outOfStock: false, sizeRequired: false, sizeSelected: false, added: false }

test('панели нет у услуг и товаров не в наличии', () => {
  assert.equal(stickyBuyBarMode({ ...base, isService: true }), 'hidden')
  assert.equal(stickyBuyBarMode({ ...base, outOfStock: true, added: true }), 'hidden')
})

test('без размера — добавить сразу, с размером — сначала выбрать', () => {
  assert.equal(stickyBuyBarMode(base), 'add')
  assert.equal(stickyBuyBarMode({ ...base, sizeRequired: true }), 'choose_size')
  assert.equal(stickyBuyBarMode({ ...base, sizeRequired: true, sizeSelected: true }), 'add')
})

test('после добавления панель ведёт в Список заявки', () => {
  assert.equal(stickyBuyBarMode({ ...base, sizeRequired: true, added: true }), 'go_to_cart')
})

test('панель видна, пока кнопка ниже экрана или уже прокручена вверх', () => {
  assert.equal(isActionBlockOffscreen({ top: 1500, bottom: 1700 }, 812, 72), true)
  assert.equal(isActionBlockOffscreen({ top: 760, bottom: 900 }, 812, 72), true)
  assert.equal(isActionBlockOffscreen({ top: 300, bottom: 500 }, 812, 72), false)
  assert.equal(isActionBlockOffscreen({ top: -400, bottom: -10 }, 812, 72), true)
  assert.equal(isActionBlockOffscreen(null, 812, 72), false)
})
