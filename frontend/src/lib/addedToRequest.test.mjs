import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import i18next from 'i18next'

import { addedToRequestStore, isCartPath, pickAddedItem, requestTotal } from './addedToRequest.js'

const state = () => addedToRequestStore.getState()

test('drawer opens with the added item and closes keeping the content for the exit animation', () => {
  const payload = { item: { id: 7, product_name: 'Кроссовки' }, total: null, trigger: null }
  state().open(payload, '/product/shoes/krossovki')
  assert.equal(state().isOpen, true)
  assert.equal(state().payload, payload)

  state().close()
  assert.equal(state().isOpen, false)
  assert.equal(state().payload, payload)
})

test('drawer does not open on the request list page', () => {
  state().close()
  for (const path of ['/cart', '/cart/', '/en/cart', '/cart?utm_source=cart_reminder']) {
    state().open({ item: null }, path)
    assert.equal(state().isOpen, false, path)
  }
  assert.equal(isCartPath('/cartoon'), false)
  assert.equal(isCartPath('/product/medicines/cart'), false)
  assert.equal(isCartPath(undefined), false)
})

test('added item is the most recently saved cart item', () => {
  const cart = {
    items: [
      { id: 1, updated_at: '2026-11-18T10:00:00Z' },
      { id: 2, updated_at: '2026-11-18T10:05:00Z' },
      { id: 3, updated_at: '2026-11-18T09:00:00Z' },
    ],
  }
  assert.equal(pickAddedItem(cart).id, 2)
  assert.equal(pickAddedItem({ items: [] }), null)
  assert.equal(pickAddedItem({ items_count: 2 }), null)
  assert.equal(pickAddedItem(undefined), null)
})

test('request total is shown only when the server sent a positive amount', () => {
  assert.deepEqual(requestTotal({ final_amount: '1500.00', total_amount: '1700.00', currency: 'RUB' }), { amount: '1500.00', currency: 'RUB' })
  assert.deepEqual(requestTotal({ total_amount: 12.5, currency: 'USD' }), { amount: 12.5, currency: 'USD' })
  assert.equal(requestTotal({ total_amount: '0.00', currency: 'RUB' }), null)
  assert.equal(requestTotal({ total_amount: '100.00' }), null)
  assert.equal(requestTotal({ items_count: 1 }), null)
  assert.equal(requestTotal(null), null)
})

// Склонения — строки из локалей, формы числа как на сайте (i18next)
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
const summary = (locale, count) => i18n.getFixedT(locale)('added_drawer_summary', { count })

test('request summary declines the number of items', () => {
  assert.deepEqual(
    [1, 2, 4, 5, 11, 12, 21, 22, 25, 101, 111].map((n) => summary('ru', n)),
    [
      'В заявке 1 товар', 'В заявке 2 товара', 'В заявке 4 товара', 'В заявке 5 товаров',
      'В заявке 11 товаров', 'В заявке 12 товаров', 'В заявке 21 товар', 'В заявке 22 товара',
      'В заявке 25 товаров', 'В заявке 101 товар', 'В заявке 111 товаров',
    ],
  )
  assert.deepEqual(
    [1, 2, 11].map((n) => summary('en', n)),
    ['1 item in your request', '2 items in your request', '11 items in your request'],
  )
})

test('every drawer string exists in both locales', () => {
  for (const key of ['added_drawer_title', 'added_drawer_close', 'added_drawer_continue', 'added_drawer_note', 'go_to_request']) {
    assert.ok(locales.ru[key], `ru ${key}`)
    assert.ok(locales.en[key], `en ${key}`)
  }
})
