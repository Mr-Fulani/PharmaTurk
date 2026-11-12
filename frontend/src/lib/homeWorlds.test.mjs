import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const read = (path) => readFile(new URL(`../../${path}`, import.meta.url), 'utf8')

test('у строки преимуществ и блоков разделов есть переводы на обоих языках', async () => {
  const sources = (await read('src/components/HomeBenefits.tsx')) + (await read('src/components/HomeCategoryWorlds.tsx'))
  const keys = [...new Set([...sources.matchAll(/t\('([a-z_]+)'/g)].map((match) => match[1]))]
  assert.ok(keys.length >= 15)
  for (const locale of ['ru', 'en']) {
    const strings = JSON.parse(await read(`public/locales/${locale}/common.json`))
    for (const key of keys) assert.ok(strings[key], `${locale}: нет перевода ${key}`)
  }
})

test('строка преимуществ: сроки как на всём сайте, оплата на сайте не обещается', async () => {
  const ru = JSON.parse(await read('public/locales/ru/common.json'))
  // DEVELOPMENT_RULES §5.10: лекарства и БАДы — 3–14 дней, остальные товары — 7–14 дней.
  assert.match(ru.home_benefit_delivery_text, /3–14 дней/)
  assert.match(ru.home_benefit_delivery_text, /7–14 дней/)
  assert.match(ru.home_benefit_request_text, /Онлайн-оплаты нет/)
})

test('ссылка на форму «Найдём товар» ведёт на якорь, который есть в HTML главной', async () => {
  const home = await read('src/pages/index.tsx')
  // Сама форма подгружается только рядом с экраном — якорь стоит на обёртке блока.
  assert.ok(home.includes("homeBlocks.includes('sourcing') ? '/#sourcing-block' : '/how-to-order-medicines#sourcing'"))
  assert.match(home, /<div id="sourcing-block" className="scroll-mt-24">\s*<DeferredSection>/)
})

test('разделы: аптека отдельно, остальные плитками и строкой ссылок', async () => {
  const home = await read('src/pages/index.tsx')
  assert.ok(home.includes("const PHARMACY_SLUGS = ['medicines', 'supplements']"))
  // Разделы без плитки не пропадают: они идут строкой «Другие разделы».
  assert.ok(home.includes('rootCategories.slice(14).map'))
  const worlds = await read('src/components/HomeCategoryWorlds.tsx')
  assert.ok(worlds.includes('others.map') && worlds.includes('href="/categories"'))
})
