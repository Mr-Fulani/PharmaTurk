import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import { buildHowToOrderSchemas } from './howToOrder.js'

const locales = Object.fromEntries(await Promise.all(['ru', 'en'].map(async (locale) => [
  locale,
  JSON.parse(await readFile(new URL(`../../public/locales/${locale}/common.json`, import.meta.url), 'utf8')),
])))

const faqs = [{ q: 'Нужен ли рецепт?', a: 'Для рецептурных — может потребоваться.' }]
const breadcrumbs = [
  { href: '/', label: 'Главная' },
  { href: '/categories/medicines', label: 'Лекарства' },
  { href: '/how-to-order-medicines', label: 'Как заказать' },
]

test('FAQPage repeats visible questions and answers', () => {
  const [faq] = buildHowToOrderSchemas({ siteUrl: 'https://mudaroba.com', localePrefix: '', faqs, breadcrumbs })
  assert.equal(faq['@type'], 'FAQPage')
  assert.deepEqual(faq.mainEntity, [{
    '@type': 'Question',
    name: faqs[0].q,
    acceptedAnswer: { '@type': 'Answer', text: faqs[0].a },
  }])
})

test('BreadcrumbList uses locale prefix only for en and never /ru', () => {
  const urls = (localePrefix) => buildHowToOrderSchemas({ siteUrl: 'https://mudaroba.com', localePrefix, faqs, breadcrumbs })[1]
    .itemListElement.map((item) => item.item)
  assert.deepEqual(urls(''), [
    'https://mudaroba.com',
    'https://mudaroba.com/categories/medicines',
    'https://mudaroba.com/how-to-order-medicines',
  ])
  assert.deepEqual(urls('/en'), [
    'https://mudaroba.com/en',
    'https://mudaroba.com/en/categories/medicines',
    'https://mudaroba.com/en/how-to-order-medicines',
  ])
})

test('how-to-order texts exist in both locales and never offer to sell medicines', () => {
  const keys = (locale) => Object.keys(locales[locale]).filter((key) => key.startsWith('hto_')).sort()
  assert.deepEqual(keys('ru'), keys('en'))
  assert.ok(keys('ru').length > 50)
  // Вопрос «Можно ли купить…» допустим: ответ на него — «нет, сайт не продаёт лекарства»
  for (const key of keys('ru').filter((k) => k !== 'hto_faq_q1')) {
    assert.doesNotMatch(locales.ru[key], /купить|купите|продаём|продаем|в продаже/i, key)
    assert.doesNotMatch(locales.en[key], /\bbuy\b|\bwe sell\b|for sale/i, key)
  }
  assert.equal(locales.ru.medicine_how_to_order_button, 'Как заказать')
  assert.equal(locales.en.medicine_how_to_order_button, 'How to order')
})
