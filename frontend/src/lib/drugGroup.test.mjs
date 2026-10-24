import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildDrugGroupSchemas,
  drugGroupHeading,
  drugGroupTranslation,
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

test('JSON-LD: Drug без Offer, рецептурность и крошки с префиксом локали', () => {
  const [drug, breadcrumbs] = buildDrugGroupSchemas({
    siteUrl: 'https://mudaroba.com',
    localePrefix: '/en',
    path: '/drugs/majezik',
    heading: 'MAJEZIK',
    latin: 'MAJEZIK',
    ingredient: 'flurbiprofen',
    description: 'd',
    prescription: true,
    breadcrumbs: [{ href: '/', label: 'Home' }, { href: '/drugs/majezik', label: 'MAJEZIK' }],
  })
  assert.equal(drug['@type'], 'Drug')
  assert.equal(drug.offers, undefined)
  assert.equal(drug.alternateName, undefined)
  assert.equal(drug.activeIngredient, 'flurbiprofen')
  assert.equal(drug.prescriptionStatus, 'https://schema.org/PrescriptionOnly')
  assert.equal(drug.url, 'https://mudaroba.com/en/drugs/majezik')
  assert.deepEqual(breadcrumbs.itemListElement.map((item) => item.item), ['https://mudaroba.com/en', 'https://mudaroba.com/en/drugs/majezik'])
})
