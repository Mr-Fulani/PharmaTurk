import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import { THEMES, THEME_BROWSER_COLOR } from './siteAppearance.js'

// Страницы товара, заявки и служебные в темах «Изник» и «Зелёная аптека»
// (docs/DESIGN_THEMES.md, «Что ещё красит тема»). Правила привязаны к теме:
// «Кремовая» и ночной режим должны остаться как были.

const read = (path) => readFile(new URL(`../../${path}`, import.meta.url), 'utf8')
const css = await read('styles/globals.css')
const SKINNED = "html:is([data-skin='iznik'], [data-skin='green']):not(.dark)"

test('разделы инструкции на странице товара берут цвета из переменных темы', async () => {
  const names = ['--accordion-bg', '--accordion-bg-hover', '--accordion-open-bg', '--accordion-border']
  for (const selector of [':root', SKINNED, '.dark']) {
    const body = css.match(new RegExp(`\\n${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')} \\{([^}]*--accordion-bg:[^}]*)\\}`))
    assert.ok(body, `нет переменных аккордеона в ${selector}`)
    for (const name of names) assert.ok(body[1].includes(`${name}:`), `${selector}: нет ${name}`)
  }
  // «Кремовая» — прежние тёплые оттенки.
  assert.match(css, /--accordion-bg: #fff8e7;\s*--accordion-bg-hover: #fff5dc;\s*--accordion-open-bg: #fffbf0;/)

  const product = await read('src/pages/product/[[...slug]].tsx')
  assert.ok(product.includes('bg-[var(--accordion-bg)]') && product.includes('bg-[var(--accordion-open-bg)]'))
  assert.ok(!/#FFF8E7|#FFF5DC|#FFFBF0/i.test(product), 'на странице товара остался жёстко заданный тёплый фон')
})

test('фиолетовое сводится к акценту только в темах, не в «Кремовой» и не ночью', () => {
  const rules = [...css.matchAll(/^(.*violet-[^{]*)\{/gm)].map((match) => match[1].trim())
  const themed = rules.filter((selector) => selector.startsWith('html'))
  assert.ok(themed.length >= 8)
  for (const selector of themed) assert.ok(selector.startsWith(`${SKINNED} `), `правило не привязано к теме: ${selector}`)
  for (const name of ['.border-violet-500', '.border-violet-600', '.ring-violet-300', '.bg-violet-600', '.bg-violet-50']) {
    assert.ok(themed.some((selector) => selector.includes(name)), `нет правила для ${name}`)
  }
})

test('кнопка cookie-баннера: акцент темы только в темах', async () => {
  const banner = await read('src/components/CookieBanner.module.css')
  assert.ok(banner.includes(`:global(${SKINNED}) .btnAccept {`))
  assert.match(banner, /\n\.btnAccept \{\s*background: linear-gradient\(135deg, #6366f1, #8b5cf6\);/)
})

test('цвет панели браузера: акцент темы, у «Кремовой» прежний', async () => {
  assert.deepEqual(Object.keys(THEME_BROWSER_COLOR), [...THEMES])
  assert.equal(THEME_BROWSER_COLOR.cream, '#4c1d95')
  for (const skin of ['iznik', 'green']) {
    const start = css.indexOf(`html[data-skin='${skin}']:not(.dark) {`)
    const accent = css.slice(start, css.indexOf('}', start)).match(/--accent:\s*(#[0-9a-f]{6});/)[1]
    assert.equal(THEME_BROWSER_COLOR[skin], accent)
  }
  const document = await read('src/pages/_document.tsx')
  assert.ok(document.includes('<meta name="theme-color" content={THEME_BROWSER_COLOR[skin || DEFAULT_THEME]} />'))
})

test('плашка «Хит» на странице товара — из тех же переменных, что на карточке товара', async () => {
  const product = await read('src/pages/product/[[...slug]].tsx')
  assert.ok(product.includes('bg-[var(--badge-bg)]') && product.includes('text-[var(--badge-text)]'))
})
