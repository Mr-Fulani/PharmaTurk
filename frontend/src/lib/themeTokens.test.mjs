import assert from 'node:assert/strict'
import { access, readFile } from 'node:fs/promises'
import test from 'node:test'

// Темы оформления — наборы значений одних и тех же переменных в styles/globals.css
// (docs/DESIGN_THEMES.md). Тема, в которой переменная забыта, молча берёт значение
// «Кремовой»: персиковый фон или рукописный шрифт посреди другой темы.

const css = await readFile(new URL('../../styles/globals.css', import.meta.url), 'utf8')

const SKINS = ['iznik', 'green']
const PALETTE = ['--bg', '--text', '--text-strong', '--surface', '--border', '--accent', '--accent-strong', '--accent-soft', '--accent-muted', '--text-hover', '--card-bg', '--card-radius', '--card-shadow', '--card-shadow-hover', '--badge-bg', '--badge-text', '--badge-ring']
const FONTS = ['--font-body', '--font-plain']

function block(selector) {
  const start = css.indexOf(`${selector} {`)
  assert.notEqual(start, -1, `нет блока ${selector}`)
  return css.slice(start, css.indexOf('}', start))
}

function declared(body) {
  return [...body.matchAll(/(--[a-z-]+)\s*:/g)].map(match => match[1])
}

test('«Кремовая» (:root) задаёт все переменные, которые меняют темы', () => {
  const names = declared(block(':root'))
  for (const name of [...PALETTE, ...FONTS]) assert.ok(names.includes(name), `в :root нет ${name}`)
})

for (const skin of SKINS) {
  test(`тема ${skin}: палитра задана целиком и только для светлого режима`, () => {
    assert.deepEqual(declared(block(`html[data-skin='${skin}']:not(.dark)`)).sort(), [...PALETTE].sort())
  })

  test(`тема ${skin}: шрифты заданы и их файлы лежат в public/fonts`, async () => {
    const body = block(`html[data-skin='${skin}']`)
    assert.deepEqual(declared(body).sort(), [...FONTS].sort())
    const family = body.match(/--font-body:\s*'([^']+)'/)[1]
    const face = css.match(new RegExp(`@font-face\\s*{[^}]*font-family:\\s*'${family}'[^}]*}`))
    assert.ok(face, `нет @font-face для ${family}`)
    assert.match(face[0], /font-display:\s*swap/)
    const file = face[0].match(/url\('(\/fonts\/[^']+\.woff2)'\)/)[1]
    await access(new URL(`../../public${file}`, import.meta.url))
  })
}

test('плашка «Хит» на карточке берёт цвета темы, а не розовый', async () => {
  const card = await readFile(new URL('../components/ProductCard.tsx', import.meta.url), 'utf8')
  assert.ok(!/(bg|text|ring)-pink-\d/.test(card), 'в карточке остался жёстко заданный розовый')
  assert.ok(card.includes('bg-[var(--badge-bg)]') && card.includes('text-[var(--badge-text)]') && card.includes('ring-[var(--badge-ring)]'))
})

test('цвет из переменной темы используется без модификатора прозрачности', async () => {
  for (const file of ['ProductCard.tsx', 'PopularProductsCarousel.tsx']) {
    const source = await readFile(new URL(`../components/${file}`, import.meta.url), 'utf8')
    assert.ok(source.includes('bg-[var(--card-bg)]'), `${file}: карточка не на --card-bg`)
    assert.ok(source.includes('product-card ') && source.includes('rounded-[var(--card-radius)]'), `${file}: скругление и тень карточки должны идти от темы`)
    assert.ok(!/shadow-\[var\(--card-shadow/.test(source), `${file}: Tailwind принимает shadow-[var(--…)] за цвет — тень задаёт класс product-card`)
    assert.ok(!/\[var\(--card-bg\)\]\/\d/.test(source), `${file}: --card-bg с прозрачностью Tailwind не сгенерирует`)
  }
})
