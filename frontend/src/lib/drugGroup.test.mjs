import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildDrugGroupFaq,
  buildDrugGroupSchemas,
  drugGroupHeading,
  drugGroupTranslation,
  faqAnswerText,
  formatIsoDate,
  joinSentencesWithin,
  lowestPrice,
  splitParagraphs,
} from './drugGroup.js'

test('заголовок: кириллица и латиница, без повтора одинакового названия', () => {
  assert.equal(drugGroupHeading({ name: 'Мажезик', latin: 'MAJEZIK' }), 'Мажезик (MAJEZIK)')
  assert.equal(drugGroupHeading({ name: 'Majezik', latin: 'MAJEZIK' }), 'MAJEZIK')
  assert.equal(drugGroupHeading({ name: '', latin: 'MAJEZIK' }), 'MAJEZIK')
})

test('перевод — только на языке страницы, без текста другого языка', () => {
  const group = { translations: [{ locale: 'ru', name: 'Мажезик' }] }
  assert.equal(drugGroupTranslation(group, 'ru').name, 'Мажезик')
  assert.deepEqual(drugGroupTranslation(group, 'en'), {})
})

test('абзацы через пустую строку', () => {
  assert.deepEqual(splitParagraphs('Первый\nабзац.\n\n  Второй.  \n\n'), ['Первый абзац.', 'Второй.'])
})

test('цена «от» — самая низкая из форм с ценой', () => {
  assert.deepEqual(
    lowestPrice([{ price: null, currency: 'RUB' }, { price: '951.9', currency: 'RUB' }, { price: 539.62, currency: 'RUB' }, { price: 0 }]),
    { price: 539.62, currency: 'RUB' },
  )
  assert.equal(lowestPrice([{ price: null }]), null)
})

test('описание: предложение, которое не помещается, пропускается целиком', () => {
  const text = joinSentencesWithin(['Начало.', 'Длинное предложение, которое не войдёт.', '', 'Хвост.'], 20)
  assert.equal(text, 'Начало. Хвост.')
})

test('дата без часового пояса', () => {
  assert.equal(formatIsoDate('2026-10-24T23:59:00+03:00'), '24.10.2026')
  assert.equal(formatIsoDate(null), '')
})

test('JSON-LD: без Drug (нет Offer и рейтинга — ошибка товара в Google), крошки с префиксом локали', () => {
  const schemas = buildDrugGroupSchemas({
    siteUrl: 'https://mudaroba.com',
    localePrefix: '/en',
    breadcrumbs: [{ href: '/', label: 'Home' }, { href: '/drugs/majezik', label: 'MAJEZIK' }],
  })
  assert.deepEqual(schemas.map((schema) => schema['@type']), ['BreadcrumbList'])
  assert.deepEqual(schemas[0].itemListElement.map((item) => item.item), ['https://mudaroba.com/en', 'https://mudaroba.com/en/drugs/majezik'])
})

// Как next-i18next без загруженных переводов: фолбэк с подстановкой {{параметров}}
const fakeT = (key, fallback, params = {}) => fallback.replace(/\{\{(\w+)\}\}/g, (_, name) => String(params[name]))

test('FAQ препарата: цена, формы, доставка, как заказать — со ссылкой на «Как заказать»', () => {
  const faq = buildDrugGroupFaq({
    heading: 'Мажезик (MAJEZIK)',
    priceText: '546 RUB',
    forms: [{ name: 'MAJEZIK 100 мг, 30 таблеток' }, { name: 'MAJEZIK спрей' }],
    t: fakeT,
  })
  assert.deepEqual(faq.map((item) => item.question), [
    'Сколько стоит Мажезик (MAJEZIK)?',
    'В каких формах выпускается Мажезик (MAJEZIK)?',
    'Сколько идёт доставка?',
    'Как заказать Мажезик (MAJEZIK)?',
  ])
  assert.match(faq[0].answer, /^Цена Мажезик \(MAJEZIK\) в Турции — от 546 RUB\./)
  assert.equal(faq[1].answer, 'Формы и дозировки на сайте: MAJEZIK 100 мг, 30 таблеток; MAJEZIK спрей.')
  assert.equal(faq[3].link.href, '/how-to-order-medicines')
  assert.equal(faqAnswerText(faq[3]), `${faq[3].answer} ${faq[3].link.label}`)
})

test('FAQ препарата: без цены и форм — «по запросу», вопроса о формах нет; длинный список сокращается', () => {
  const noData = buildDrugGroupFaq({ heading: 'X', priceText: '', forms: [], t: fakeT })
  assert.equal(noData.length, 3)
  assert.match(noData[0].answer, /по запросу/)
  const many = buildDrugGroupFaq({
    heading: 'X',
    priceText: '',
    forms: Array.from({ length: 12 }, (_, i) => ({ name: `F${i + 1}` })),
    t: fakeT,
  })
  assert.equal(many[1].answer, 'Формы и дозировки на сайте: F1; F2; F3; F4; F5; F6; F7; F8; F9; F10 и ещё 2.')
})

test('FAQPage в разметке совпадает с видимыми вопросами и ответами', () => {
  const faq = buildDrugGroupFaq({ heading: 'X', priceText: '1 USD', forms: [{ name: 'X 1 мг' }], t: fakeT })
  const schemas = buildDrugGroupSchemas({
    siteUrl: 'https://mudaroba.com',
    localePrefix: '',
    breadcrumbs: [{ href: '/', label: 'Главная' }],
    faq,
  })
  assert.deepEqual(schemas.map((schema) => schema['@type']), ['BreadcrumbList', 'FAQPage'])
  assert.deepEqual(
    schemas[1].mainEntity.map((q) => [q.name, q.acceptedAnswer.text]),
    faq.map((item) => [item.question, faqAnswerText(item)]),
  )
})
