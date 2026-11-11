import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import i18next from 'i18next'

import { appendSentenceIfShort, buildCategoryDescription, limitTitle, productImageAlt, splitSeoText, truncateAtWord, withProductTitleSuffix } from './seoText.js'

test('short text is returned as is with collapsed whitespace', () => {
  assert.equal(truncateAtWord('  Аспирин   500  ', 200), 'Аспирин 500')
})

test('long text is cut at the last whole word with ellipsis', () => {
  const result = truncateAtWord('Успейте приобрести модели из лайкры и плащевой ткани', 30)
  assert.equal(result, 'Успейте приобрести модели из…')
  assert.ok(result.length <= 30)
})

test('whole last word right at the limit is kept', () => {
  assert.equal(truncateAtWord('abc def ghi', 8), 'abc def…')
})

test('trailing punctuation before ellipsis is dropped', () => {
  assert.equal(truncateAtWord('Буркини для бассейна, удлинённая модель', 24), 'Буркини для бассейна…')
})

test('one huge token is hard-cut instead of collapsing to nothing', () => {
  const result = truncateAtWord(`a ${'x'.repeat(50)}`, 20)
  assert.equal(result.length, 20)
  assert.ok(result.endsWith('…'))
})

test('title keeps category and site suffix and shortens only the name', () => {
  const name = 'Успейте приобрести по очень выгодной цене модели из лайкры и из плащевой ткани для бассейна'
  const result = limitTitle(`${name} | Mudaroba`, 70)
  assert.ok(result.length <= 70)
  assert.ok(result.endsWith('… | Mudaroba'))
  assert.equal(limitTitle(`${name} | Буркини | Mudaroba`, 70).endsWith('… | Буркини | Mudaroba'), true)
})

test('short title is untouched', () => {
  assert.equal(limitTitle('Аспирин | Медикаменты | Mudaroba', 70), 'Аспирин | Медикаменты | Mudaroba')
})

test('short brand description gets the template as a separate sentence', () => {
  const suffix = 'Adidas из Турции с доставкой.'
  assert.equal(appendSentenceIfShort('Немецкий спортивный бренд.', suffix), 'Немецкий спортивный бренд. Adidas из Турции с доставкой.')
  assert.equal(appendSentenceIfShort('Spor markası', suffix), 'Spor markası. Adidas из Турции с доставкой.')
  assert.equal(appendSentenceIfShort('', suffix), suffix)
  const long = 'x '.repeat(40).trim()
  assert.equal(appendSentenceIfShort(long, suffix), long)
})

test('category description adds count, subcategories and tail to a short base', () => {
  const text = buildCategoryDescription({
    base: 'Обувь всех видов',
    lead: 'Обувь из Турции с доставкой',
    countText: '674 товара',
    subcategories: ['Кроссовки', 'Сандалии', 'Туфли', 'Ботинки'],
    tail: 'Оригинальные товары, актуальные цены, заказ через менеджера Mudaroba',
  })
  assert.equal(
    text,
    'Обувь из Турции с доставкой — 674 товара: Кроссовки, Сандалии, Туфли. Обувь всех видов. ' +
      'Оригинальные товары, актуальные цены, заказ через менеджера Mudaroba.'
  )
  assert.ok(text.length <= 160)
})

test('category description drops a base that does not fit and keeps long manual text', () => {
  const parts = {
    lead: 'Медицина из Турции с доставкой',
    countText: '12 142 товара',
    subcategories: ['Антибиотики', 'Обезболивающие', 'Витамины'],
    tail: 'Оригинальные товары, актуальные цены, заказ через менеджера Mudaroba',
  }
  const withoutRoom = buildCategoryDescription({ ...parts, base: 'Лекарственные препараты и медикаменты для взрослых и детей' })
  assert.ok(!withoutRoom.includes('Лекарственные'))
  assert.ok(withoutRoom.length <= 160)
  const manual = 'Развёрнутое описание раздела, написанное вручную администратором, '.repeat(2).trim()
  assert.equal(buildCategoryDescription({ ...parts, base: manual }), truncateAtWord(`${manual}.`, 160))
})


test('seo text splits into paragraphs and ## headings', () => {
  const text = '## Что в разделе\nПервый абзац\nс переносом.\n\n\nВторой абзац.\r\n\r\n## Как заказать\nТретий.'
  assert.deepEqual(splitSeoText(text), [
    { kind: 'heading', text: 'Что в разделе' },
    { kind: 'paragraph', text: 'Первый абзац с переносом.' },
    { kind: 'paragraph', text: 'Второй абзац.' },
    { kind: 'heading', text: 'Как заказать' },
    { kind: 'paragraph', text: 'Третий.' },
  ])
})

test('empty seo text gives no blocks', () => {
  assert.deepEqual(splitSeoText(''), [])
  assert.deepEqual(splitSeoText(null), [])
  assert.deepEqual(splitSeoText('##   \n\n  '), [])
})

test('product image alt uses the page-language name, not the stored Turkish alt', () => {
  const storedAlt = 'adidas Samba OG Unisex Beyaz Spor Ayakkabı - Белый - фото 2'
  const name = 'Кроссовки унисекс adidas Samba OG, белые'
  assert.equal(productImageAlt({ name, storedAlt, index: 0 }), name)
  assert.equal(productImageAlt({ name, storedAlt, index: 1 }), `${name} — фото 2`)
  assert.equal(productImageAlt({ name: 'Sneakers', storedAlt, index: 2, photoLabel: 'photo' }), 'Sneakers — photo 3')
  assert.equal(productImageAlt({ name: '', storedAlt, index: 1 }), storedAlt)
})

const RU = { fromTurkey: 'из Турции', siteName: 'Mudaroba' }
const EN = { fromTurkey: 'from Turkey', siteName: 'Mudaroba' }

test('title товара: дописывается «из Турции | Mudaroba», слова не убираются, пока влезает в 80', () => {
  assert.equal(withProductTitleSuffix('Свитшот LC Waikiki', RU), 'Свитшот LC Waikiki из Турции | Mudaroba')
  assert.equal(
    withProductTitleSuffix('Свитшот LC Waikiki - стильная одежда для мужчин', RU),
    'Свитшот LC Waikiki - стильная одежда для мужчин из Турции | Mudaroba',
  )
  assert.equal(
    withProductTitleSuffix("LC Waikiki Sweatshirt - Stylish Men's Clothing", EN),
    "LC Waikiki Sweatshirt - Stylish Men's Clothing from Turkey | Mudaroba",
  )
  // «купить с доставкой из Турции» сохраняется: 62 + 11 ≤ 80
  assert.equal(
    withProductTitleSuffix('Мужская футболка Tommy Hilfiger — купить с доставкой из Турции', RU),
    'Мужская футболка Tommy Hilfiger — купить с доставкой из Турции | Mudaroba',
  )
})

test('title товара: Турция уже есть — только « | Mudaroba»; сайт уже есть — без изменений', () => {
  assert.equal(
    withProductTitleSuffix('Мирена (MIRENA, левоноргестрел), внутриматочная система из Турции', RU),
    'Мирена (MIRENA, левоноргестрел), внутриматочная система из Турции | Mudaroba',
  )
  assert.equal(withProductTitleSuffix('Кроссовки | Обувь | Mudaroba', RU), 'Кроссовки | Обувь | Mudaroba')
  // Длинный шаблон с сайтом по-прежнему режется до 80, хвост « | Категория | Mudaroba» сохраняется
  const longDefault = `${'Очень длинное название из поста Instagram '.repeat(3).trim()} | Одежда | Mudaroba`
  const limited = withProductTitleSuffix(longDefault, RU)
  assert.ok(limited.length <= 80, limited)
  assert.ok(limited.endsWith('… | Одежда | Mudaroba'), limited)
  // «турецкий» — Турция уже есть; «Turkuaz» (бирюзовый) — нет
  assert.equal(withProductTitleSuffix('Турецкий кофе Mehmet Efendi', RU), 'Турецкий кофе Mehmet Efendi | Mudaroba')
  assert.equal(withProductTitleSuffix('Turkuaz Elbise', EN), 'Turkuaz Elbise from Turkey | Mudaroba')
  assert.equal(withProductTitleSuffix('', RU), '')
})

test('title товара длиннее 80: режется описание (Турция остаётся), не название; «Men\'s» не висит', () => {
  const long = 'Двухместный диван-кровать IKEA LYCKSELE LÖVÅS — купить с доставкой и сборкой по выгодной цене'
  const result = withProductTitleSuffix(long, RU)
  assert.ok(result.length <= 80, result)
  assert.ok(result.startsWith('Двухместный диван-кровать IKEA LYCKSELE LÖVÅS'))
  assert.ok(result.endsWith('из Турции | Mudaroba'), result)
  assert.equal(
    withProductTitleSuffix("Very Long Brand Name Cotton Sweatshirt Hoodie Model 2026 - Stylish Men's Clothing", EN),
    'Very Long Brand Name Cotton Sweatshirt Hoodie Model 2026 from Turkey | Mudaroba',
  )
})

test('title товара без описательной части длиннее 80: сначала без «из Турции», потом обрезка', () => {
  const long = 'Очень длинное название товара без разделителя описания примерно на семьдесят символов'
  const result = withProductTitleSuffix(long, RU)
  assert.ok(result.length <= 80, result)
  assert.ok(result.endsWith(' | Mudaroba'))
  const huge = 'Х'.repeat(10) + ' ' + 'слово '.repeat(20)
  const cut = withProductTitleSuffix(huge, RU)
  assert.ok(cut.length <= 80 && cut.endsWith('… | Mudaroba'), cut)
})

// Шаблон описания раздела: строки берутся из локалей, формы числа — как на сайте (i18next).
const metaLocales = Object.fromEntries(await Promise.all(['ru', 'en'].map(async (locale) => [
  locale,
  JSON.parse(await readFile(new URL(`../../public/locales/${locale}/common.json`, import.meta.url), 'utf8')),
])))
const metaI18n = i18next.createInstance()
await metaI18n.init({
  lng: 'ru',
  resources: { ru: { translation: metaLocales.ru }, en: { translation: metaLocales.en } },
  interpolation: { escapeValue: false },
})
const metaCount = (locale, key, count) => metaI18n.getFixedT(locale)(key, { count, formattedCount: String(count) })

test('service category description: no delivery, counts services, own tail (RU/EN)', () => {
  assert.deepEqual(
    [1, 2, 5, 11, 21, 104].map((n) => metaCount('ru', 'service_category_meta_count', n)),
    ['1 услуга', '2 услуги', '5 услуг', '11 услуг', '21 услуга', '104 услуги']
  )
  assert.deepEqual(
    [1, 2, 16].map((n) => metaCount('en', 'service_category_meta_count', n)),
    ['1 service', '2 services', '16 services']
  )
  const ru = buildCategoryDescription({
    base: '',
    lead: 'Кондиционеры',
    countText: metaCount('ru', 'service_category_meta_count', 2),
    subcategories: ['Установка кондиционера', 'Демонтаж кондиционера'],
    tail: metaLocales.ru.service_category_meta_tail,
  })
  assert.equal(
    ru,
    'Кондиционеры — 2 услуги: Установка кондиционера, Демонтаж кондиционера. ' +
      'Опишите задачу — менеджер Mudaroba подберёт исполнителя и назовёт стоимость.'
  )
  const en = buildCategoryDescription({
    base: '',
    lead: 'Air Conditioners',
    countText: metaCount('en', 'service_category_meta_count', 2),
    subcategories: ['AC Installation', 'AC Removal'],
    tail: metaLocales.en.service_category_meta_tail,
  })
  assert.equal(
    en,
    'Air Conditioners — 2 services: AC Installation, AC Removal. ' +
      'Describe your task — a Mudaroba manager will find a contractor and quote the price.'
  )
  for (const text of [ru, en, metaLocales.ru.services_found, metaLocales.en.services_found]) {
    assert.doesNotMatch(text, /товар|доставк|оригинал|product|deliver|original/i)
  }
})

test('goods category description template is unchanged', () => {
  assert.equal(metaLocales.ru.category_meta_lead, '{{category}} из Турции с доставкой')
  assert.equal(metaLocales.ru.category_meta_tail, 'Оригинальные товары, актуальные цены, заказ через менеджера Mudaroba')
  assert.equal(metaLocales.en.category_meta_lead, '{{category}} from Turkey with delivery')
  assert.equal(metaLocales.en.category_meta_tail, 'Original products, current prices, ordering via a Mudaroba manager')
  assert.deepEqual(
    [1, 3, 5, 21].map((n) => metaCount('ru', 'category_meta_count', n)),
    ['1 товар', '3 товара', '5 товаров', '21 товар']
  )
  assert.deepEqual([1, 16].map((n) => metaCount('en', 'category_meta_count', n)), ['1 product', '16 products'])
  assert.equal(metaLocales.ru.products_found, 'НАЙДЕНО ТОВАРОВ')
  assert.equal(metaLocales.en.products_found, 'PRODUCTS FOUND')
})

test('pages pick the service wording by product type, not by name', async () => {
  const [categoryPage, productPage, reviews] = await Promise.all([
    readFile(new URL('../pages/categories/[slug].tsx', import.meta.url), 'utf8'),
    readFile(new URL('../pages/product/[[...slug]].tsx', import.meta.url), 'utf8'),
    readFile(new URL('../components/ProductReviews.tsx', import.meta.url), 'utf8'),
  ])
  assert.match(categoryPage, /const isServiceCategory = categoryType === 'uslugi'/)
  assert.match(categoryPage, /t\(isServiceCategory \? 'service_category_meta_count' : 'category_meta_count'/)
  assert.match(categoryPage, /isServiceCategory\s*\? t\('service_category_meta_tail'[^\n]*\n\s*: t\('category_meta_tail'/)
  // У услуги в разметке нет артикула и «в наличии», в og — не «product»
  assert.match(productPage, /\.\.\.\(!isService && \{ sku: resolveSchemaSku/)
  assert.match(productPage, /\.\.\.\(!isService && \{ availability \}\)/)
  assert.match(productPage, /og:type" content=\{isService \? 'website' : 'product'\}/)
  assert.match(reviews, /const isService = productType === 'uslugi'/)
})
