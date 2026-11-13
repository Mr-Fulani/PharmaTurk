import assert from 'node:assert/strict'
import { readdir, readFile } from 'node:fs/promises'
import test from 'node:test'

import { BIG_SCREEN_FROM, BIG_SCREEN_MAX_ZOOM, LAPTOP_WIDTH, bigScreenZoom } from './pageWidth.js'

// Большие мониторы: страница как на ноутбуке, только крупнее (docs/DESIGN_THEMES.md, «Большие мониторы»).

const root = new URL('../../', import.meta.url)
const read = (path) => readFile(new URL(path, root), 'utf8')
const css = await read('styles/globals.css')

async function sources(dir = 'src/') {
  const files = []
  for (const entry of await readdir(new URL(dir, root), { withFileTypes: true })) {
    if (entry.isDirectory()) files.push(...(await sources(`${dir}${entry.name}/`)))
    else if (/\.(tsx?|jsx?)$/.test(entry.name) && !entry.name.includes('.test.')) files.push(`${dir}${entry.name}`)
  }
  return files
}

test('масштаб: до 1759 px его нет (все MacBook), дальше ширина окна / 1440, не больше двух раз', () => {
  assert.equal(bigScreenZoom(1440), 1)
  // MacBook Air 15″ — 1710 px, MacBook Pro 16″ — 1728 px: вид прежний.
  assert.equal(bigScreenZoom(1710), 1)
  assert.equal(bigScreenZoom(1728), 1)
  assert.equal(bigScreenZoom(1759), 1)
  assert.equal(bigScreenZoom(1760), 1.2222)
  assert.equal(bigScreenZoom(1920), 1.3333)
  assert.equal(bigScreenZoom(2560), 1.7778)
  assert.equal(bigScreenZoom(3840), BIG_SCREEN_MAX_ZOOM)
})

test('ступени масштаба в стилях совпадают с формулой и идут по возрастанию', () => {
  const steps = [...css.matchAll(/@media \(min-width: (\d+)px\) \{\s*:root \{\s*--page-zoom: ([\d.]+);/g)].map((match) => [Number(match[1]), Number(match[2])])
  assert.ok(steps.length >= 6)
  assert.equal(steps[0][0], BIG_SCREEN_FROM)
  assert.equal(steps.at(-1)[1], BIG_SCREEN_MAX_ZOOM)
  let previous = 0
  for (const [width, zoom] of steps) {
    assert.ok(width > previous, 'ступени не по возрастанию — сработала бы меньшая')
    assert.equal(zoom, bigScreenZoom(width), `ступень ${width}px`)
    // Между ступенями содержимое не шире окна: страница шириной width / zoom ≥ 1440 px.
    assert.ok(width / zoom >= LAPTOP_WIDTH - 1)
    previous = width
  }
  assert.match(css, /--page-zoom: 1;/)
  assert.match(css, new RegExp(`@media \\(min-width: ${BIG_SCREEN_FROM}px\\) \\{\\s*html \\{\\s*zoom: var\\(--page-zoom\\);`))
})

test('ширина страницы одна на всех экранах: расширения и лишних колонок для больших мониторов нет', async () => {
  assert.match(css, /:root \{\s*--page-max: 72rem;\s*--page-max-wide: 80rem;\s*\}/)
  assert.equal(css.split('--page-max:').length - 1, 1, 'ширину страницы меняет ещё какое-то правило')
  const offenders = []
  for (const file of await sources()) {
    const source = await read(file)
    if (/max-w-(6xl|7xl|screen-xl|screen-2xl)\b|\b3xl:|\b4xl:/.test(source)) offenders.push(file)
  }
  assert.deepEqual(offenders, [], 'контейнер страницы — max-w-page или max-w-page-wide, без отдельной вёрстки для больших мониторов')
})

test('высота экрана и ширина окна при масштабе делятся на масштаб', async () => {
  // Каждый размер в vh, который встречается в классах, перекрыт в правилах большого монитора.
  const used = new Set()
  for (const file of await sources()) {
    for (const match of (await read(file)).matchAll(/(?:^|[\s"'`])((?:[a-z]+:)?(?:min-h|max-h|h)-(?:screen|\[[^\]\s]*vh[^\]\s]*\]))/g)) used.add(match[1])
  }
  assert.ok(used.has('min-h-screen'))
  for (const cls of used) {
    const selector = `.${cls.replace(/[:[\]()]/g, '\\$&')} {`
    assert.ok(css.includes(selector), `класс ${cls} при масштабе вырастет выше экрана — добавьте правило в globals.css`)
  }
  assert.ok((await read('src/components/CategoryHero.tsx')).split('width: calc(100vw / var(--page-zoom, 1));').length - 1 === 2)
  assert.ok((await read('src/pages/404.tsx')).includes('min-height: calc(100vh / var(--page-zoom, 1));'))
})

test('координаты окна переводятся в пиксели страницы там, где код ставит элементы сам', async () => {
  const widget = await read('src/components/ContactWidget.tsx')
  assert.equal(widget.split('window.innerWidth / pageZoom()').length - 1, 2)
  assert.equal(widget.split('window.innerHeight / pageZoom()').length - 1, 2)
  assert.ok(widget.includes('(event.clientX - dragState.startX) / pageZoom()') && widget.includes('(event.clientY - dragState.startY) / pageZoom()'))
  const share = await read('src/components/ShareButton.tsx')
  assert.ok(share.includes('x: (rect.left + rect.width / 2) / zoom') && share.includes('y: (rect.top + rect.height / 2) / zoom'))
})
