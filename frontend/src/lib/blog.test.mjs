import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import { BLOG_ARTICLES, DRUG_GROUP_ARTICLE_SLUGS, IMPORT_ARTICLE_SLUG, getBlogArticle } from '../content/blog/articles.js'
import { articleLinks, articleText, buildArticleSchemas } from './blog.js'

const LOCALES = ['ru', 'en']
// SEO-план медикаментов, «Ограничения»: не обещать продажу и выдачу без рецепта
const BANNED_PHRASES = ['без рецепта', 'без назначения', 'купить', 'without a prescription', 'without prescription', 'over the counter', 'buy ']
// Не называть препараты и вещества, запрещённые к ввозу в РФ и СНГ, и бренды, в линейке которых
// они есть (TD-024, решение PR #165 в MEDICINE_LANDING_PAGES.md)
const BANNED_NAMES = [
  'fentan', 'фентан', 'kodein', 'codein', 'кодеин', 'efedrin', 'ephedrin', 'эфедрин', 'pregabalin', 'прегабалин',
  'tramadol', 'трамадол', 'durogesic', 'perge', 'pagamax', 'tylolhot', 'katarin forte', 'a-ferin sinus', 'a-ferin plus',
  'aerius', 'эриус', 'a-ferin', 'а-ферин', 'katarin', 'катарин', 'parol', 'broksin',
  'nurofen cold', 'pedifen cold', 'ergotamin', 'эрготамин',
]
const groupSlugs = [...(await readFile(new URL('../../../backend/apps/catalog/migrations/0225_medicine_group_texts.py', import.meta.url), 'utf8'))
  .matchAll(/"slug": "([a-z0-9-]+)"/g)].map((match) => match[1])

test('у каждой статьи оба языка, мета в пределах длины и вопросы для FAQPage', () => {
  assert.deepEqual(BLOG_ARTICLES.map((item) => item.slug).sort(), [
    'kak-proverit-tureckoe-lekarstvo', 'pravila-vvoza-lekarstv-iz-turcii', 'top-tureckih-lekarstv', 'tureckie-analogi-lekarstv',
  ])
  for (const item of BLOG_ARTICLES) {
    for (const locale of LOCALES) {
      const article = item[locale]
      assert.ok(article.title && article.lead && article.sections.length, `${item.slug} ${locale}`)
      // SEO.tsx дописывает « — Mudaroba»: всего не больше 80 символов
      assert.ok(article.metaTitle.length <= 80 - ' — Mudaroba'.length, `${item.slug} ${locale} title ${article.metaTitle.length}`)
      assert.ok(article.description.length <= 200, `${item.slug} ${locale} description ${article.description.length}`)
      assert.ok(article.faq.length >= 3, `${item.slug} ${locale} faq`)
    }
    assert.equal(item.ru.faq.length, item.en.faq.length, item.slug)
  }
})

test('тексты не обещают выдачу без рецепта и не называют запрещённые к ввозу препараты', () => {
  for (const item of BLOG_ARTICLES) {
    for (const locale of LOCALES) {
      const text = articleText(item[locale]).toLowerCase()
      for (const phrase of [...BANNED_PHRASES, ...BANNED_NAMES]) {
        assert.ok(!text.includes(phrase), `${item.slug} ${locale}: «${phrase}»`)
      }
    }
  }
})

test('ссылки статей ведут на свои страницы, страницы препаратов существуют', () => {
  assert.ok(groupSlugs.includes('majezik') && !groupSlugs.includes('tylolhot'))
  const blogSlugs = BLOG_ARTICLES.map((item) => item.slug)
  for (const item of BLOG_ARTICLES) {
    for (const locale of LOCALES) {
      for (const href of articleLinks(item[locale])) {
        assert.ok(href.startsWith('/') && !href.startsWith('/ru/') && !href.startsWith('/en/'), `${item.slug}: ${href}`)
        const drug = href.match(/^\/drugs\/(.+)$/)
        if (drug) assert.ok(groupSlugs.includes(drug[1]), `${item.slug}: нет препарата ${drug[1]}`)
        const blog = href.match(/^\/blog\/(.+)$/)
        if (blog) assert.ok(blogSlugs.includes(blog[1]), `${item.slug}: нет статьи ${blog[1]}`)
      }
    }
  }
  for (const slug of [...DRUG_GROUP_ARTICLE_SLUGS, IMPORT_ARTICLE_SLUG]) assert.ok(blogSlugs.includes(slug), slug)
})

test('JSON-LD статьи: Article, FAQPage по видимым вопросам, крошки с префиксом локали', () => {
  const article = getBlogArticle('pravila-vvoza-lekarstv-iz-turcii', 'en')
  const breadcrumbs = [{ href: '/', label: 'Home' }, { href: '/blog', label: 'Articles' }, { href: `/blog/${article.slug}`, label: article.title }]
  const [main, faq, crumbs] = buildArticleSchemas({
    siteUrl: 'https://mudaroba.com', siteName: 'Mudaroba', localePrefix: '/en', article, locale: 'en', breadcrumbs,
  })
  assert.equal(main['@type'], 'Article')
  assert.equal(main.url, 'https://mudaroba.com/en/blog/pravila-vvoza-lekarstv-iz-turcii')
  assert.equal(main.dateModified, '2026-10-24')
  assert.equal(faq['@type'], 'FAQPage')
  assert.deepEqual(faq.mainEntity.map((item) => item.name), article.faq.map((item) => item.q))
  assert.equal(crumbs['@type'], 'BreadcrumbList')
  assert.equal(crumbs.itemListElement[0].item, 'https://mudaroba.com/en')
})
