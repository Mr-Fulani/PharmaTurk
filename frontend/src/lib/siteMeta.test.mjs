import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'

const source = await readFile(new URL('./siteMeta.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const meta = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

test('withSiteName appends the site name once', () => {
  assert.equal(meta.withSiteName('Доставка и оплата'), 'Доставка и оплата — Mudaroba')
})

test('withSiteName does not duplicate a site name already present in CMS titles', () => {
  assert.equal(meta.withSiteName('Доставка и оплата — Mudaroba'), 'Доставка и оплата — Mudaroba')
  assert.equal(meta.withSiteName('О нас — Mudaroba | Товары из Турции'), 'О нас — Mudaroba | Товары из Турции')
})

test('withSiteName falls back to the site name for empty titles', () => {
  assert.equal(meta.withSiteName('  '), 'Mudaroba')
})
