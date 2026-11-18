import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import i18next from 'i18next'

import { addConflictOffer, addConflictRetryParams, askConfirm, confirmDialogStore } from './confirmDialog.js'

const state = () => confirmDialogStore.getState()
const question = { title: 'Очистить заявку?', lines: [], acceptLabel: 'Очистить', declineLabel: 'Отмена' }

test('the dialog resolves with the answer and closes', async () => {
  const accepted = askConfirm(question)
  assert.equal(state().request.title, 'Очистить заявку?')
  state().answer(true)
  assert.equal(await accepted, true)
  assert.equal(state().request, null)

  const declined = askConfirm(question)
  state().answer(false)
  assert.equal(await declined, false)
  // ответ без вопроса ничего не ломает
  state().answer(true)
  assert.equal(state().request, null)
})

test('a new question on top of an unanswered one declines the old one', async () => {
  const first = askConfirm(question)
  const second = askConfirm({ ...question, title: 'Цена изменилась' })
  assert.equal(await first, false)
  assert.equal(state().request.title, 'Цена изменилась')
  state().answer(true)
  assert.equal(await second, true)
})

// Ответ 409 /orders/cart/add в формате apps/orders/views.py::_cart_verification_error_response
const conflict = (codes, verification) => ({
  detail: 'x',
  code: codes[0],
  issues: codes.map((code) => ({ code, message: code, blocking: true })),
  verification: { status: 'blocked', available_quantity: null, public_price: null, public_currency: '', ...verification },
})

test('price change: accepting re-sends the same request with the acknowledged price', () => {
  const offer = addConflictOffer(conflict(['source_price_changed'], { public_price: '2599.90', public_currency: 'TRY' }))
  assert.deepEqual(offer, { price: '2599.90', currency: 'TRY' })
  assert.deepEqual(addConflictRetryParams(offer), { acknowledged_price: '2599.90', acknowledged_currency: 'TRY' })
})

test('quantity change: accepting re-sends the request with the available quantity', () => {
  const offer = addConflictOffer(conflict(['source_quantity_changed'], { available_quantity: 2 }))
  assert.deepEqual(offer, { quantity: 2 })
  assert.deepEqual(addConflictRetryParams(offer), { quantity: '2' })
})

test('both changes are one question and one retry', () => {
  const offer = addConflictOffer(conflict(
    ['source_quantity_changed', 'source_price_changed'],
    { available_quantity: 1, public_price: 1500, public_currency: 'RUB' },
  ))
  assert.deepEqual(offer, { quantity: 1, price: '1500', currency: 'RUB' })
  assert.deepEqual(addConflictRetryParams(offer), { quantity: '1', acknowledged_price: '1500', acknowledged_currency: 'RUB' })
})

test('nothing to ask: the error is shown as is', () => {
  assert.equal(addConflictOffer(conflict(['source_out_of_stock'], {})), null)
  // количество изменилось, но поставщик не сообщил сколько, или товара нет совсем
  assert.equal(addConflictOffer(conflict(['source_quantity_changed'], { available_quantity: null })), null)
  assert.equal(addConflictOffer(conflict(['source_quantity_changed'], { available_quantity: 0 })), null)
  // цена изменилась, но без валюты подтверждать нечего
  assert.equal(addConflictOffer(conflict(['source_price_changed'], { public_price: '10.00', public_currency: '' })), null)
  assert.equal(addConflictOffer(null), null)
  assert.equal(addConflictOffer({ detail: 'Недостаточно товара в наличии', available: 3 }), null)
})

const locales = Object.fromEntries(await Promise.all(['ru', 'en'].map(async (locale) => [
  locale,
  JSON.parse(await readFile(new URL(`../../public/locales/${locale}/common.json`, import.meta.url), 'utf8')),
])))
const i18n = i18next.createInstance()
await i18n.init({
  lng: 'ru',
  resources: { ru: { translation: locales.ru }, en: { translation: locales.en } },
  interpolation: { escapeValue: false },
})

test('dialog strings exist in both locales and decline the number of items', () => {
  for (const key of [
    'confirm_add_price_title', 'confirm_add_price_text', 'confirm_add_price_accept',
    'confirm_add_quantity_title', 'confirm_add_quantity_text', 'confirm_add_quantity_accept',
    'confirm_add_both_title', 'confirm_add_both_accept', 'confirm_add_decline',
    'confirm_clear_title', 'confirm_clear_accept', 'confirm_remove_title', 'remove', 'cancel',
  ]) {
    assert.ok(locales.ru[key], `ru ${key}`)
    assert.ok(locales.en[key], `en ${key}`)
  }
  assert.deepEqual(
    [1, 3, 5, 21].map((count) => i18n.getFixedT('ru')('confirm_clear_text', { count })),
    [
      'В заявке 1 товар. Вернуть его будет нельзя.', 'В заявке 3 товара. Вернуть их будет нельзя.',
      'В заявке 5 товаров. Вернуть их будет нельзя.', 'В заявке 21 товар. Вернуть его будет нельзя.',
    ],
  )
  assert.deepEqual(
    [1, 2].map((count) => i18n.getFixedT('en')('confirm_clear_text', { count })),
    ['It has 1 item. This cannot be undone.', 'It has 2 items. This cannot be undone.'],
  )
  assert.equal(i18n.getFixedT('ru')('confirm_add_quantity_accept', { count: 2 }), 'Добавить 2 шт.')
  // системных окон не осталось: старые тексты убраны
  for (const key of ['cart_confirm_remove', 'cart_confirm_clear', 'cart_confirm_price_change', 'cart_confirm_quantity_change']) {
    assert.equal(locales.ru[key], undefined)
    assert.equal(locales.en[key], undefined)
  }
})

test('no browser confirm() is left in the add button and the request page', async () => {
  for (const file of ['../components/AddToCartButton.tsx', '../pages/cart.tsx']) {
    const source = await readFile(new URL(file, import.meta.url), 'utf8')
    assert.doesNotMatch(source, /\bconfirm\(/, file)
  }
})
