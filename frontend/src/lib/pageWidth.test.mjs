import assert from 'node:assert/strict'
import { readdir, readFile } from 'node:fs/promises'
import test from 'node:test'

import { WIDE_SCREEN, wideMasonryColumns } from './pageWidth.js'

// Ширина страницы на больших мониторах (docs/DESIGN_THEMES.md, «Ширина страницы»).

const root = new URL('../../', import.meta.url)
const read = (path) => readFile(new URL(path, root), 'utf8')

async function sources(dir = 'src/') {
  const files = []
  for (const entry of await readdir(new URL(dir, root), { withFileTypes: true })) {
    if (entry.isDirectory()) files.push(...(await sources(`${dir}${entry.name}/`)))
    else if (/\.(tsx?|jsx?)$/.test(entry.name) && !entry.name.includes('.test.')) files.push(`${dir}${entry.name}`)
  }
  return files
}

test('ширина страницы задана одной парой переменных: ноутбук прежний, большие мониторы шире и одинаково', async () => {
  const css = await read('styles/globals.css')
  assert.match(css, /:root \{\s*--page-max: 72rem;\s*--page-max-wide: 80rem;\s*\}/)
  assert.match(css, new RegExp(`@media \\(min-width: ${WIDE_SCREEN}px\\) \\{\\s*:root \\{\\s*--page-max: 90rem;\\s*--page-max-wide: 90rem;`))
  // 90rem = 1440 px, минус боковые отступы — не шире баннера (1400 px): контент и баннеры главной одной ширины.
  assert.match(await read('src/components/BannerCarousel.module.css'), /\.container \{[^}]*max-width: 1400px;/)

  const config = await read('tailwind.config.js')
  assert.ok(config.includes("page: 'var(--page-max)'") && config.includes("'page-wide': 'var(--page-max-wide)'"))
  assert.ok(config.includes(`'3xl': '${WIDE_SCREEN}px'`))
})

test('страницы не задают свою ширину контейнера в обход общей', async () => {
  const offenders = []
  for (const file of await sources()) {
    if (/max-w-(6xl|7xl|screen-xl|screen-2xl)\b/.test(await read(file))) offenders.push(file)
  }
  assert.deepEqual(offenders, [], 'контейнер страницы — max-w-page или max-w-page-wide')
})

test('шапка, строка разделов, подвал и главная стоят на общей ширине', async () => {
  for (const file of ['src/components/Header.tsx', 'src/components/SectionNav.tsx', 'src/components/Footer.tsx', 'src/pages/index.tsx']) {
    assert.match(await read(file), /mx-auto (w-full |flex )?max-w-page /, `${file}: нет общей ширины`)
  }
})

test('кладка «Все бренды» и «Все категории»: три колонки на ноутбуке, больше на большом мониторе', async () => {
  assert.equal(wideMasonryColumns(1440), 3)
  assert.equal(wideMasonryColumns(1919), 3)
  assert.equal(wideMasonryColumns(1920), 4)
  assert.equal(wideMasonryColumns(2560), 4)
  for (const file of ['src/pages/brands/index.tsx', 'src/pages/categories/index.tsx']) {
    const page = await read(file)
    assert.ok(page.includes('breakpointCols={{ default: desktopColumns, 1024: 3, 768: 2, 640: 1 }}'), `${file}: колонки не из хука`)
  }
  // Сервер и первый кадр — три колонки: на ноутбуке и телефоне вёрстка после загрузки не перестраивается.
  assert.ok((await read('src/hooks/useWideMasonryColumns.ts')).includes('useState(3)'))
})

test('сетки товаров добавляют колонку на большом мониторе', async () => {
  for (const [file, cls] of [
    ['src/pages/categories/[slug].tsx', 'lg:grid-cols-3 3xl:grid-cols-4'],
    ['src/pages/brand/[slug].tsx', 'lg:grid-cols-3 3xl:grid-cols-4'],
    ['src/pages/favorites.tsx', 'lg:grid-cols-3 3xl:grid-cols-4'],
    ['src/pages/search.tsx', 'lg:grid-cols-4 3xl:grid-cols-5'],
  ]) assert.ok((await read(file)).includes(cls), `${file}: нет ${cls}`)
})
