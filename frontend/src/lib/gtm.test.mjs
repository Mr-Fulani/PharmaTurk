import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('./gtm.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const gtm = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

test('ga4EventParams flattens ecommerce payload for gtag', () => {
  assert.deepEqual(
    gtm.ga4EventParams({
      event: 'purchase',
      ecommerce: { currency: 'RUB', value: 1500, transaction_id: 'A1', items: [{ item_id: 1, item_name: 'X' }] },
    }),
    { currency: 'RUB', value: 1500, transaction_id: 'A1', items: [{ item_id: 1, item_name: 'X' }] },
  )
})

test('ga4EventParams keeps custom parameters and drops the event name', () => {
  assert.deepEqual(
    gtm.ga4EventParams({ event: 'sourcing_request', placement: 'home' }),
    { placement: 'home' },
  )
})
