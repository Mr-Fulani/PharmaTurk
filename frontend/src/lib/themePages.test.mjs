import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import { THEMES, THEME_BROWSER_COLOR } from './siteAppearance.js'

// Страницы товара, заявки и служебные в темах «Изник» и «Зелёная аптека»
// (docs/DESIGN_THEMES.md, «Что ещё красит тема»). Правила привязаны к теме:
// «Кремовая» — и днём, и ночью — должна остаться как была.

const read = (path) => readFile(new URL(`../../${path}`, import.meta.url), 'utf8')
const css = await read('styles/globals.css')
const SKINNED = "html:is([data-skin='iznik'], [data-skin='green'])"

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

test('фиолетовое сводится к акценту только в темах, не в «Кремовой»', () => {
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

// Ночной режим тем (решение владельца 13.11.2026: у каждой темы свой).
const NIGHT = ['--bg', '--text', '--text-strong', '--surface', '--border', '--accent', '--accent-strong', '--accent-soft', '--accent-muted', '--text-hover', '--card-radius', '--card-shadow', '--card-shadow-hover', '--badge-bg', '--badge-text', '--badge-ring', '--accordion-bg', '--accordion-bg-hover', '--accordion-open-bg']

function block(selector) {
  const start = css.indexOf(`${selector} {`)
  assert.notEqual(start, -1, `нет блока ${selector}`)
  return css.slice(start, css.indexOf('}', start))
}
const value = (body, name) => body.match(new RegExp(`${name}:\\s*([^;]+);`))?.[1]

function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

for (const skin of ['iznik', 'green']) {
  test(`тема ${skin}: ночной набор задан целиком и читается`, () => {
    const night = block(`html[data-skin='${skin}'].dark`)
    const day = block(`html[data-skin='${skin}']:not(.dark)`)
    assert.deepEqual([...night.matchAll(/(--[a-z-]+)\s*:/g)].map((match) => match[1]).sort(), [...NIGHT].sort())
    // Основной текст на фоне и на блоках — не ниже 7:1.
    assert.ok(contrast(value(night, '--text'), value(night, '--bg')) >= 7)
    assert.ok(contrast(value(night, '--text'), value(night, '--surface')) >= 7)
    // Акцент — и текст на тёмном фоне, и фон кнопки с белой подписью: не ниже 4:1 в обе стороны.
    assert.ok(contrast(value(night, '--accent'), value(night, '--bg')) >= 4)
    assert.ok(contrast('#ffffff', value(night, '--accent')) >= 4)
    // Светлые плашки и форма карточки ночью те же, что днём (так устроен и общий ночной режим).
    for (const name of ['--accent-soft', '--accent-muted', '--card-radius', '--badge-bg', '--badge-text', '--badge-ring']) {
      assert.equal(value(night, name), value(day, name), `${name} ночью отличается от дневного`)
    }
  })
}

test('у «Кремовой» ночной набор общий: отдельного блока нет', () => {
  assert.ok(!css.includes("html[data-skin='cream'].dark"))
})
