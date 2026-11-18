import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import i18next from 'i18next'

import {
  addedToRequestStore, drawerRows, drawerThumbUrl, isCartPath, orderDrawerItems, pickAddedItem, requestTotal, undoAddParams,
} from './addedToRequest.js'

const state = () => addedToRequestStore.getState()

test('drawer opens with the added item and closes keeping the content for the exit animation', () => {
  const payload = { cart: { items: [{ id: 7, product_name: 'Кроссовки' }] }, addedId: 7, trigger: null }
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
    state().open({ cart: null }, path)
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
  for (const key of [
    'added_drawer_title', 'added_drawer_close', 'added_drawer_continue', 'added_drawer_note', 'go_to_request',
    'added_drawer_removed', 'added_drawer_undo', 'added_drawer_error', 'added_drawer_undo_error',
    'remove', 'cart_decrease_quantity', 'cart_increase_quantity', 'cart_empty', 'cart_empty_description',
    'size', 'price_on_request',
  ]) {
    assert.ok(locales.ru[key], `ru ${key}`)
    assert.ok(locales.en[key], `en ${key}`)
  }
})

test('drawer thumbnail asks for a small copy of our CDN photo and leaves other urls alone', () => {
  assert.equal(
    drawerThumbUrl('https://mudaroba.com/api/catalog/proxy-image/?url=https%3A//cdn.mudaroba.com/products/shoes/a%20b/photo.jpg'),
    '/api/catalog/proxy-media/?path=products%2Fshoes%2Fa%20b%2Fphoto.jpg&max_width=192',
  )
  for (const url of [
    'https://mudaroba.com/api/catalog/proxy-image/?url=https%3A//scontent.cdninstagram.com/p.jpg',
    '/api/catalog/proxy-media/?path=products%2Fa.jpg',
    'https://example.com/a.jpg',
    '/product-placeholder.svg',
    '',
  ]) {
    assert.equal(drawerThumbUrl(url), url)
  }
})

test('auto-close stops for good after the first interaction and starts again on the next opening', () => {
  state().open({ cart: { items: [] } }, '/')
  assert.equal(state().engaged, false)
  state().engage()
  assert.equal(state().engaged, true)
  state().close()
  assert.equal(state().engaged, true)
  state().open({ cart: { items: [] } }, '/')
  assert.equal(state().engaged, false)
  // на странице заявки панель не открывается и состояние не трогает
  state().engage()
  state().open({ cart: { items: [] } }, '/cart')
  assert.equal(state().engaged, true)
})

const ids = (items) => items.map((item) => item.id)

test('the just added item goes first, the rest keep the server order', () => {
  const items = [{ id: 1 }, { id: 2 }, { id: 3 }]
  assert.deepEqual(ids(orderDrawerItems(items, 3)), [3, 1, 2])
  assert.deepEqual(ids(orderDrawerItems(items, undefined)), [1, 2, 3])
  assert.deepEqual(orderDrawerItems(undefined, 3), [])
})

test('items do not jump after a change: the previous order wins, new items go to the end', () => {
  // сервер после смены количества вернул позиции в другом порядке и добавил новую
  const items = [{ id: 2 }, { id: 9 }, { id: 3 }, { id: 1 }]
  assert.deepEqual(ids(orderDrawerItems(items, undefined, [3, 1, 2])), [3, 1, 2, 9])
  // удалённая позиция просто пропадает из порядка
  assert.deepEqual(ids(orderDrawerItems([{ id: 2 }, { id: 3 }], undefined, [3, 1, 2])), [3, 2])
})

test('a removed item leaves an undo row in its place', () => {
  const removedItem = { id: 1, product: 55, quantity: 2, chosen_size: '38' }
  const entry = { key: 'removed-1', item: removedItem, index: 1 }
  const rows = drawerRows([{ id: 3 }, { id: 2 }], [entry])
  assert.deepEqual(rows.map((row) => row.key), ['item-3', 'removed-1', 'item-2'])
  assert.equal(rows[1].entry, entry)
  assert.equal(rows[0].entry, null)
  // заявка опустела — строка «Вернуть» остаётся единственной
  assert.deepEqual(drawerRows([], [{ ...entry, index: 4 }]).map((row) => row.key), ['removed-1'])
  assert.deepEqual(drawerRows(undefined), [])
})

test('undo re-adds the same product, size and quantity', () => {
  assert.deepEqual(undoAddParams({ id: 1, product: 55, quantity: 2, chosen_size: '38' }), { product_id: '55', quantity: '2', size: '38' })
  assert.deepEqual(undoAddParams({ id: 4, product: 7, quantity: 1, chosen_size: '' }), { product_id: '7', quantity: '1' })
})
