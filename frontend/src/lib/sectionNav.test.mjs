import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import { NAV_SECTIONS, currentNavSection } from './sectionNav.js'

const read = (path) => readFile(new URL(`../../${path}`, import.meta.url), 'utf8')

test('открытый раздел подсвечивается на странице раздела и его подборки', () => {
  assert.equal(currentNavSection('/categories/[slug]', { slug: 'medicines' }), 'medicines')
  assert.equal(currentNavSection('/categories/[slug]/[collection]', { slug: 'shoes', collection: 'x' }), 'shoes')
  // Подраздел (/categories/sneakers) и чужие страницы раздел не подсвечивают.
  assert.equal(currentNavSection('/categories/[slug]', { slug: 'sneakers' }), '')
  assert.equal(currentNavSection('/product/[[...slug]]', { slug: ['medicines'] }), '')
  assert.equal(currentNavSection('/', {}), '')
})

test('у каждого пункта строки разделов есть перевод на обоих языках', async () => {
  const keys = [...NAV_SECTIONS.map((section) => section.labelKey), 'section_nav_label', 'section_nav_all', 'footer_how_to_order', 'header_catalog']
  for (const locale of ['ru', 'en']) {
    const strings = JSON.parse(await read(`public/locales/${locale}/common.json`))
    for (const key of keys) assert.ok(strings[key], `${locale}: нет перевода ${key}`)
  }
  const ru = JSON.parse(await read('public/locales/ru/common.json'))
  for (const section of NAV_SECTIONS) assert.equal(ru[section.labelKey], section.label)
})

test('строка разделов не закреплена и не меняет отступ под шапку', async () => {
  const nav = await read('src/components/SectionNav.tsx')
  assert.ok(!/\b(fixed|sticky)\b/.test(nav.slice(nav.indexOf('<nav'))), 'строка разделов должна идти в потоке страницы')
  // Ссылки — <Link>: разделы должны быть в HTML каждой страницы.
  assert.ok(nav.includes('href={`/categories/${section.slug}`}'))

  const app = await read('src/pages/_app.tsx')
  assert.match(app, /pt-\[calc\(68px\+env\(safe-area-inset-top\)\)\] md:pt-\[calc\(72px\+env\(safe-area-inset-top\)\)\]">\s*<SectionNav \/>/)
})

test('название в шапке закреплено на широком экране одним CSS и не сдвигает строку', async () => {
  const header = await read('src/components/Header.tsx')
  const wide = '[@media(min-width:1024px)_and_(hover:hover)_and_(pointer:fine)]'
  // Одно и то же условие прячет подпись по наведению и показывает закреплённое название.
  assert.ok(header.includes(`overflow-hidden ${wide}:hidden`))
  assert.ok(header.includes(`hidden items-end whitespace-nowrap ${wide}:flex`))
  // Буквы проявляются CSS-анимацией: название в HTML с первой отрисовки, без ожидания скриптов.
  assert.ok(header.includes('className="logo-pinned-letter"'))
  const css = await read('styles/globals.css')
  assert.match(css, /\.logo-pinned-letter\s*{[^}]*animation: logo-pinned-letter-in/)
  assert.match(css, /prefers-reduced-motion: reduce\)\s*{\s*\.logo-pinned-letter\s*{\s*animation: none/)
})

test('подвал: колонка «Каталог» добавлена, прежние блоки и подсказка о криптовалюте на месте', async () => {
  const footer = await read('src/components/Footer.tsx')
  assert.ok(footer.includes('NAV_SECTIONS.map'), 'нет колонки разделов')
  // Подсказка о криптовалюте — текст из настроек у картинки способов оплаты.
  assert.ok(footer.includes('/footer-payments.webp') && footer.includes('{cryptoText}'))
  for (const href of ['/about-us', '/returns', '/delivery', '/privacy', '/how-to-order-medicines', '/dostavka-lekarstv-stambul', '/turetskaya-apteka', '/blog', '/testimonials', '/categories']) {
    assert.ok(footer.includes(`href="${href}"`), `в подвале нет ссылки ${href}`)
  }
  for (const icon of ['/telegram.svg', '/whatsapp.svg', '/vk.svg', '/instagram.svg']) assert.ok(footer.includes(icon))
  assert.ok(footer.includes('href={`tel:${phone}`}') && footer.includes('href={`mailto:${email}`}'))
  // На широком экране — четыре колонки и карточка отзывов пятой.
  assert.ok(footer.includes('lg:grid-cols-4 xl:grid-cols-5'))
})
