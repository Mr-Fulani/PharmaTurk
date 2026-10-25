import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import {
  ISTANBUL_DELIVERY,
  ISTANBUL_DELIVERY_PATH,
  buildIstanbulDeliverySchemas,
  istanbulDeliveryContent,
} from '../content/istanbulDelivery.js'

test('RU and EN pages have the same structure', () => {
  const { ru, en } = ISTANBUL_DELIVERY
  for (const key of ['badges', 'pains', 'audience', 'catalog', 'steps', 'trust', 'useful', 'faq']) {
    assert.equal(ru[key].length, en[key].length, key)
  }
  assert.deepEqual(Object.keys(ru.districts), Object.keys(en.districts))
  assert.equal(istanbulDeliveryContent('de'), ISTANBUL_DELIVERY.ru)
})

test('SEO lengths: title up to 60 chars before the site name, description up to 160', () => {
  for (const content of Object.values(ISTANBUL_DELIVERY)) {
    assert.ok(content.metaTitle.length <= 60, content.metaTitle)
    assert.ok(content.metaDescription.length <= 160, content.metaDescription)
  }
})

test('unconfirmed terms are not promised: no fixed delivery time, price or payment method', () => {
  const text = JSON.stringify(ISTANBUL_DELIVERY)
  assert.doesNotMatch(text, /\d+\s*(минут|minutes|мин\.|min)\b/i)
  assert.doesNotMatch(text, /(₺|TL|лир|\$)\s*\d|\d\s*(₺|TL|лир)/i)
  assert.doesNotMatch(text, /наличн|cash|24\/7|круглосуточно/i)
})

test('restricted substances are named and linked to the rules article', () => {
  for (const content of Object.values(ISTANBUL_DELIVERY)) {
    assert.match(content.restrictedText, /(кодеин|codeine).*(прегабалин|pregabalin)/i)
    assert.equal(content.restrictedLink.href, '/blog/pravila-vvoza-lekarstv-iz-turcii')
  }
})

test('schemas: Service in Istanbul, FAQPage matches visible questions, breadcrumbs', () => {
  const content = ISTANBUL_DELIVERY.en
  const [service, faq, breadcrumbs] = buildIstanbulDeliverySchemas({
    siteUrl: 'https://mudaroba.com', localePrefix: '/en', content, siteName: 'Mudaroba',
  })
  assert.equal(service['@type'], 'Service')
  assert.equal(service.areaServed.name, 'Istanbul')
  assert.equal(service.url, `https://mudaroba.com/en${ISTANBUL_DELIVERY_PATH}`)
  assert.deepEqual(faq.mainEntity.map((item) => item.name), content.faq.map((item) => item.q))
  assert.equal(breadcrumbs.itemListElement.at(-1).item, `https://mudaroba.com/en${ISTANBUL_DELIVERY_PATH}`)
})

test('the page is in the static sitemap', () => {
  const sitemap = readFileSync(new URL('../pages/sitemaps/[section].tsx', import.meta.url), 'utf8')
  assert.match(sitemap, new RegExp(`'${ISTANBUL_DELIVERY_PATH}'`))
})
