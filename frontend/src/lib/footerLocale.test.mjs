import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('./footerLocale.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const footerLocale = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

test('footer locale is normalized to a backend-supported language', () => {
  assert.equal(footerLocale.normalizeFooterLocale('en-US'), 'en')
  assert.equal(footerLocale.normalizeFooterLocale('en_US'), 'en')
  assert.equal(footerLocale.normalizeFooterLocale('ru-RU'), 'ru')
  assert.equal(footerLocale.normalizeFooterLocale(undefined), 'ru')
})

test('footer pages request always contains an explicit normalized language', () => {
  assert.deepEqual(footerLocale.buildFooterPagesParams('en-US'), { lang: 'en' })
  assert.deepEqual(footerLocale.buildFooterPagesParams('ru'), { lang: 'ru' })
})
