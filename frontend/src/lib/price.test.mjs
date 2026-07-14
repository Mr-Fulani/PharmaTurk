import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('./price.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const money = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

test('parses localized thousands without losing magnitude', () => {
  assert.equal(money.parseMoneyNumber('1,500.00 TRY'), 1500)
  assert.equal(money.parseMoneyNumber('1.500,00 TRY'), 1500)
  assert.equal(money.parseMoneyNumber('13 249,5 KZT'), 13249.5)
})

test('formats cents only for USD EUR and USDT', () => {
  assert.equal(money.formatMoney(14, 'USD', 'en'), '14.00')
  assert.equal(money.formatMoney(14.5, 'EUR', 'en'), '14.50')
  assert.equal(money.formatMoney(14, 'USDT', 'en'), '14.00')
  assert.equal(money.formatMoney(13249.5, 'KZT', 'en'), '13,250')
  assert.equal(money.formatMoney(2050.02, 'RUB', 'en'), '2,050')
  assert.equal(money.formatMoney(1253.5, 'TRY', 'en'), '1,254')
})

test('uses locale-specific thousands separators', () => {
  assert.match(money.formatMoney(13249.5, 'KZT', 'ru'), /^13[\s\u00a0\u202f]250$/)
  assert.equal(money.parsePriceWithCurrency('1,500.00 TRY').price, 1500)
  assert.equal(money.parsePriceWithCurrency('1,500.00 TRY').currency, 'TRY')
})
