import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import { BLOG_ARTICLES } from '../content/blog/articles.js'
import {
  TURKISH_PHARMACY,
  TURKISH_PHARMACY_BLOG_SLUGS,
  TURKISH_PHARMACY_PATH,
  buildTurkishPharmacySchemas,
  turkishPharmacyBreadcrumbs,
  turkishPharmacyContent,
} from '../content/turkishPharmacy.js'
import { articleLinks, articleText } from './blog.js'

const LOCALES = ['ru', 'en']
// Сайт не аптека и лекарства не продаёт (DEVELOPMENT_RULES §1.9, ограничения SEO-ядра)
const BANNED = [
  'без рецепта', 'без назначения', 'купить', 'аптека онлайн', 'онлайн-аптек', 'интернет-аптек',
  'without a prescription', 'without prescription', 'over the counter', 'online pharmacy',
  'режим работы',
]
const groupSlugs = [...(await readFile(new URL('../../../backend/apps/catalog/migrations/0225_medicine_group_texts.py', import.meta.url), 'utf8'))
  .matchAll(/"slug": "([a-z0-9-]+)"/g)].map((match) => match[1])

// Видимый текст в формате статьи блога: заголовок, вступление, разделы, FAQ
const asArticle = (content) => ({
  title: content.h1, metaTitle: content.metaTitle, description: content.metaDescription, lead: `${content.lead}\n${content.notice}`,
  sections: content.sections, faq: content.faq,
})

test('ru и en одной структуры, мета в пределах длины (SEO.tsx дописывает « — Mudaroba»)', () => {
  const { ru, en } = TURKISH_PHARMACY
  assert.deepEqual(ru.sections.map((s) => s.id), en.sections.map((s) => s.id))
  assert.equal(ru.faq.length, en.faq.length)
  assert.ok(ru.faq.length >= 6)
  for (const locale of LOCALES) {
    const content = TURKISH_PHARMACY[locale]
    assert.ok(content.metaTitle.length <= 80 - ' — Mudaroba'.length, `${locale} title ${content.metaTitle.length}`)
    assert.ok(content.metaDescription.length <= 200, `${locale} description ${content.metaDescription.length}`)
  }
  assert.equal(turkishPharmacyContent('de').h1, TURKISH_PHARMACY.ru.h1)
})

test('главные запросы кластера есть в мете и на странице', () => {
  const ru = TURKISH_PHARMACY.ru
  assert.match(ru.metaTitle, /^Аптека в Турции/)
  assert.match(ru.h1, /Аптеки Турции/)
  assert.match(ru.metaDescription, /турецкой аптеки/)
  const text = articleText(asArticle(ru))
  for (const phrase of ['Цены в аптеках Турции', 'eczane', 'nöbetçi', 'Государственных аптек', 'TİTCK']) {
    assert.ok(text.includes(phrase), phrase)
  }
})

test('тексты не выдают сайт за аптеку и не обещают выдачу без рецепта', () => {
  for (const locale of LOCALES) {
    // Все строки страницы: мета, поиск, кнопки, разделы, FAQ, ссылки, контакты
    const text = JSON.stringify(TURKISH_PHARMACY[locale]).toLowerCase()
    for (const phrase of BANNED) assert.ok(!text.includes(phrase), `${locale}: «${phrase}»`)
    assert.doesNotMatch(text, /\bbuy/, `${locale}: buy`)
  }
  assert.match(TURKISH_PHARMACY.ru.notice, /не аптека и лекарства не продаёт/)
  assert.match(TURKISH_PHARMACY.en.notice, /not a pharmacy and does not sell medicines/)
})

test('сроки и оплата — только подтверждённые владельцем', () => {
  for (const locale of LOCALES) {
    const text = JSON.stringify(TURKISH_PHARMACY[locale])
    assert.match(text, /7–21/)
    assert.doesNotMatch(text, /наличн|cash|банковск|bank card|crypto|крипт/i)
    // /delivery называет способы оплаты и другие сроки — со страницы на неё не ссылаемся
    assert.ok(!TURKISH_PHARMACY[locale].useful.some((item) => item.href === '/delivery'))
  }
})

test('препараты строгого учёта не доставляем, «Ввоз ограничен» — только по согласованию (как Стамбул и баннер карточки)', () => {
  const ru = JSON.stringify(TURKISH_PHARMACY.ru)
  assert.match(ru, /Препараты строгого учёта \(наркотические и психотропные\) мы не доставляем/)
  assert.match(ru, /без согласования с менеджером не выполняем/)
  const en = JSON.stringify(TURKISH_PHARMACY.en)
  assert.match(en, /We do not deliver strictly controlled medicines/)
  assert.match(en, /without agreement with a manager/)
  for (const text of [ru, en]) assert.doesNotMatch(text, /особым правилам|special rules/)
})

test('ссылки ведут на свои страницы без /ru и /en', () => {
  const blogSlugs = BLOG_ARTICLES.map((item) => item.slug)
  for (const locale of LOCALES) {
    const content = turkishPharmacyContent(locale)
    const hrefs = [...articleLinks(content), ...content.useful.map((item) => item.href)]
    for (const href of hrefs) {
      assert.ok(href.startsWith('/') && !/^\/(ru|en)(\/|$)/.test(href), `${locale}: ${href}`)
      const drug = href.match(/^\/drugs\/(.+)$/)
      if (drug) assert.ok(groupSlugs.includes(drug[1]), `${locale}: нет препарата ${drug[1]}`)
      const blog = href.match(/^\/blog\/(.+)$/)
      if (blog) assert.ok(blogSlugs.includes(blog[1]), `${locale}: нет статьи ${blog[1]}`)
    }
    for (const required of ['/categories/medicines', '/how-to-order-medicines', '/dostavka-lekarstv-stambul', '/blog/pravila-vvoza-lekarstv-iz-turcii']) {
      assert.ok(hrefs.includes(required), `${locale}: нет ссылки ${required}`)
    }
  }
  assert.equal(TURKISH_PHARMACY_BLOG_SLUGS.length, 4)
  for (const slug of TURKISH_PHARMACY_BLOG_SLUGS) assert.ok(blogSlugs.includes(slug), slug)
})

test('JSON-LD: FAQPage слово в слово с видимыми вопросами, крошки с префиксом только у en', () => {
  for (const [locale, localePrefix] of [['ru', ''], ['en', '/en']]) {
    const content = turkishPharmacyContent(locale)
    const breadcrumbs = turkishPharmacyBreadcrumbs(content, locale === 'ru' ? 'Главная' : 'Home')
    const [faq, crumbs] = buildTurkishPharmacySchemas({ siteUrl: 'https://mudaroba.com', localePrefix, content, breadcrumbs })
    assert.equal(faq['@type'], 'FAQPage')
    assert.deepEqual(faq.mainEntity.map((item) => [item.name, item.acceptedAnswer.text]), content.faq.map((item) => [item.q, item.a]))
    assert.deepEqual(crumbs.itemListElement.map((item) => item.item), [
      `https://mudaroba.com${localePrefix}`,
      `https://mudaroba.com${localePrefix}/categories/medicines`,
      `https://mudaroba.com${localePrefix}${TURKISH_PHARMACY_PATH}`,
    ])
  }
})

test('страница в sitemap (static) и в футере', async () => {
  const sitemap = await readFile(new URL('../pages/sitemaps/[section].tsx', import.meta.url), 'utf8')
  assert.ok(sitemap.includes(`['${TURKISH_PHARMACY_PATH}', '${TURKISH_PHARMACY_PATH}', 'monthly', 0.8]`))
  const footer = await readFile(new URL('../components/Footer.tsx', import.meta.url), 'utf8')
  assert.ok(footer.includes(`href="${TURKISH_PHARMACY_PATH}"`))
})
