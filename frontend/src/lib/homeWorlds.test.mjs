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

test('ряд брендов на главной не кончается пустой ячейкой', async () => {
  const home = await read('src/pages/index.tsx')
  // Ряд на flex: карточки брендов фиксированной ширины, последняя — «Все бренды» — растягивается на остаток строки.
  assert.ok(home.includes('<div className="hidden w-full flex-wrap gap-4 md:flex">'))
  assert.ok(home.includes("const BRAND_TILE_BASIS = 'basis-[calc((100%_-_3rem)/4)] lg:basis-[calc((100%_-_5rem)/6)]'"))
  assert.match(home, /\$\{BRAND_TILE_BASIS\} relative isolate aspect-\[4\/3\] shrink-0 grow-0/)
  assert.match(home, /href="\/brands"\s+className=\{`\$\{BRAND_TILE_BASIS\} group flex min-h-\[72px\] grow /)
  // Отдельной кнопки под рядом больше нет: ссылка «Все бренды» на десктопе одна.
  assert.equal(home.split('href="/brands"').length - 1, 1)
})

test('блоки разделов и их плитки — без рамок', async () => {
  const worlds = await read('src/components/HomeCategoryWorlds.tsx')
  assert.ok(!worlds.includes('border border-[var(--border)]'), 'у блока или плитки осталась рамка')
  assert.equal(worlds.split('rounded-2xl bg-[var(--surface)] p-4 md:p-6').length - 1, 2)
})
