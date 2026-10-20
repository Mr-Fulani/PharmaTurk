import assert from 'node:assert/strict'
import { mkdtemp, readFile, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import test from 'node:test'
import ts from 'typescript'

// gtm.ts импортирует ./ym — транспилируем оба модуля во временную папку
process.env.NEXT_PUBLIC_YM_ID = '123'
const outDir = await mkdtemp(join(tmpdir(), 'gtm-test-'))
for (const name of ['gtm', 'ym']) {
  const source = await readFile(new URL(`./${name}.ts`, import.meta.url), 'utf8')
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText.replace(/from '\.\/(\w+)'/g, "from './$1.mjs'")
  await writeFile(join(outDir, `${name}.mjs`), compiled)
}
const gtm = await import(pathToFileURL(join(outDir, 'gtm.mjs')).href)

/** window с перехватом gtag и ym: события уходят синхронно, без ожидания gtag. */
function mockWindow(t, pathname = '/') {
  const calls = { gtag: [], ym: [] }
  globalThis.window = {
    dataLayer: [],
    setTimeout,
    location: { pathname },
    gtag: (...args) => calls.gtag.push(args),
    ym: (...args) => calls.ym.push(args),
  }
  t.after(() => { delete globalThis.window })
  return calls
}

/** Минимальный DOM: ссылка внутри контейнера с data-analytics-placement. */
function fakeLink(href, placement) {
  const container = placement ? { getAttribute: () => placement } : null
  const link = {
    getAttribute: (name) => (name === 'href' ? href : null),
    closest: (selector) => (selector === '[data-analytics-placement]' ? container : null),
  }
  const icon = { closest: (selector) => (selector === 'a[href]' ? link : null) }
  return { target: icon }
}

test('ga4EventParams flattens ecommerce payload for gtag', () => {
  assert.deepEqual(
    gtm.ga4EventParams({
      event: 'purchase',
      ecommerce: { currency: 'RUB', value: 1500, transaction_id: 'A1', items: [{ item_id: 1, item_name: 'X' }] },
    }),
    { currency: 'RUB', value: 1500, transaction_id: 'A1', items: [{ item_id: 1, item_name: 'X' }] },
  )
})

test('ga4EventParams keeps custom parameters and drops the event name', () => {
  assert.deepEqual(
    gtm.ga4EventParams({ event: 'sourcing_request', placement: 'home' }),
    { placement: 'home' },
  )
})

test('gtmEvent waits for gtag that loads after the event fired', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const calls = []
  globalThis.window = { dataLayer: [], setTimeout }
  t.after(() => { delete globalThis.window })

  gtm.gtmEvent({ event: 'view_item', ecommerce: { currency: 'USD', items: [{ item_id: 1, item_name: 'X' }] } })
  t.mock.timers.tick(400)
  window.gtag = (...args) => calls.push(args)
  t.mock.timers.tick(200)

  assert.deepEqual(calls, [['event', 'view_item', { currency: 'USD', items: [{ item_id: 1, item_name: 'X' }] }]])
})

test('gtmEvent gives up when gtag never loads (no analytics consent)', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  globalThis.window = { dataLayer: [], setTimeout }
  t.after(() => { delete globalThis.window })

  gtm.gtmEvent({ event: 'view_item' })
  // повторные таймеры создаются внутри tick — идём шагами по 200 мс
  for (let i = 0; i < 30; i += 1) t.mock.timers.tick(200)
  window.gtag = () => assert.fail('event must not be sent after the wait window')
  for (let i = 0; i < 30; i += 1) t.mock.timers.tick(200)
})


test('contactChannelFromHref recognises contact links and skips share links', () => {
  const cases = {
    'tel:+905525821497': 'phone',
    'mailto:info@mudaroba.com': 'email',
    'https://wa.me/905525821497': 'whatsapp',
    'http://wa.me/905525821497?text=hi': 'whatsapp',
    'https://api.whatsapp.com/send?phone=905525821497': 'whatsapp',
    'https://t.me/mudaroba': 'telegram',
    'https://vk.com/mudaroba': 'vk',
    'https://wa.me/?text=https%3A%2F%2Fmudaroba.com': null,
    'https://t.me/share/url?url=https%3A%2F%2Fmudaroba.com': null,
    'https://vk.com/share.php?url=x': null,
    '/categories/medicines': null,
    '': null,
  }
  for (const [href, channel] of Object.entries(cases)) {
    assert.equal(gtm.contactChannelFromHref(href), channel, href)
  }
})

test('contact link click anywhere on the site goes to GA4 and Metrika with placement', (t) => {
  const calls = mockWindow(t, '/delivery')
  gtm.handleContactLinkClick(fakeLink('https://wa.me/905525821497', 'footer'))
  gtm.handleContactLinkClick(fakeLink('tel:+905525821497'))

  assert.deepEqual(calls.gtag, [
    ['event', 'contact_click', { contact_channel: 'whatsapp', placement: 'footer' }],
    ['event', 'contact_click', { contact_channel: 'phone', placement: 'page' }],
  ])
  assert.deepEqual(calls.ym, [
    [123, 'reachGoal', 'click_whatsapp', { placement: 'footer' }],
    [123, 'reachGoal', 'click_phone', { placement: 'page' }],
  ])
})

test('contact links of users in profiles and ordinary links are not tracked', (t) => {
  const calls = mockWindow(t, '/en/user/ivan')
  gtm.handleContactLinkClick(fakeLink('https://wa.me/79990000000'))
  window.location.pathname = '/catalog'
  gtm.handleContactLinkClick(fakeLink('/product/x'))
  assert.deepEqual(calls.gtag, [])
  assert.deepEqual(calls.ym, [])
})

test('order request is a lead, not a purchase', (t) => {
  const calls = mockWindow(t)
  gtm.gtmGenerateLead({ source: 'order', value: 1500, currency: 'RUB', transactionId: 'A-17', paymentMethod: 'manager' })

  assert.deepEqual(calls.gtag, [['event', 'generate_lead', {
    lead_source: 'order', value: 1500, currency: 'RUB', transaction_id: 'A-17', payment_method: 'manager',
  }]])
  const goalParams = { lead_source: 'order', order_price: 1500, currency: 'RUB' }
  assert.deepEqual(calls.ym, [
    [123, 'reachGoal', 'generate_lead', goalParams],
    [123, 'reachGoal', 'order_request', goalParams],
  ])
  assert.ok(!window.dataLayer.some((entry) => entry.event === 'purchase'))
})

test('sourcing request is a lead with the form placement', (t) => {
  const calls = mockWindow(t)
  gtm.gtmGenerateLead({ source: 'sourcing', placement: 'how_to_order' })

  assert.deepEqual(calls.gtag, [['event', 'generate_lead', { lead_source: 'sourcing', placement: 'how_to_order' }]])
  assert.deepEqual(calls.ym.map((call) => call[2]), ['generate_lead', 'sourcing_request'])
})

test('gtmProductItem uses base product id for base types and slug for the rest', () => {
  assert.deepEqual(
    gtm.gtmProductItem({ id: 7, base_product_id: 70, slug: 'majezik', name: 'Majezik' }, 'medicines', true),
    { item_id: 70, item_name: 'Majezik', item_category: 'medicines' },
  )
  assert.deepEqual(
    gtm.gtmProductItem({ id: 8, slug: 'krossovki-nike', name: 'Nike' }, 'shoes', false),
    { item_id: 'krossovki-nike', item_name: 'Nike', item_category: 'shoes' },
  )
})

test('view_item_list numbers items and skips empty lists', (t) => {
  const calls = mockWindow(t)
  gtm.gtmViewItemList({ id: 'category:medicines', name: 'Медицина' }, [])
  gtm.gtmViewItemList({ id: 'category:medicines', name: 'Медицина' }, [
    { item_id: 1, item_name: 'A', item_category: 'medicines' },
    { item_id: 2, item_name: 'B', item_category: 'medicines' },
  ])

  assert.deepEqual(calls.gtag, [['event', 'view_item_list', {
    item_list_id: 'category:medicines',
    item_list_name: 'Медицина',
    items: [
      { item_id: 1, item_name: 'A', item_category: 'medicines', index: 0 },
      { item_id: 2, item_name: 'B', item_category: 'medicines', index: 1 },
    ],
  }]])
  assert.deepEqual(window.dataLayer.slice(-2)[0], { ecommerce: null })
})

test('add_to_cart carries price and value; buy now has its own Metrika goal', (t) => {
  const calls = mockWindow(t)
  gtm.gtmAddToCart({ item_id: 5, item_name: 'X', item_category: 'supplements', price: 200 }, 3, 'RUB', 'buy_now')

  assert.deepEqual(calls.gtag, [['event', 'add_to_cart', {
    currency: 'RUB', value: 600, items: [{ item_id: 5, item_name: 'X', item_category: 'supplements', price: 200, quantity: 3 }],
  }]])
  assert.deepEqual(calls.ym, [[123, 'reachGoal', 'buy_now', undefined]])
})

test('add_to_wishlist goes to GA4 and Metrika', (t) => {
  const calls = mockWindow(t)
  gtm.gtmAddToWishlist({ item_id: 9, item_name: 'Y', item_category: 'clothing', price: 50 }, 'USD')

  assert.deepEqual(calls.gtag, [['event', 'add_to_wishlist', {
    currency: 'USD', value: 50, items: [{ item_id: 9, item_name: 'Y', item_category: 'clothing', price: 50, quantity: 1 }],
  }]])
  assert.deepEqual(calls.ym, [[123, 'reachGoal', 'add_to_wishlist', undefined]])
})
