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

test('gtmEvent waits for gtag that loads after the event fired', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const calls = []
  globalThis.window = { dataLayer: [], setTimeout }
  t.after(() => { delete globalThis.window })

  gtm.gtmEvent({ event: 'view_item', ecommerce: { currency: 'USD', items: [{ item_id: 1, item_name: 'X' }] } })
  t.mock.timers.tick(400)
  window.gtag = (...args) => calls.push(args)
  t.mock.timers.tick(200)

  assert.deepEqual(calls, [['event', 'view_item', { currency: 'USD', items: [{ item_id: 1, item_name: 'X' }] }]])
})

test('gtmEvent gives up when gtag never loads (no analytics consent)', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  globalThis.window = { dataLayer: [], setTimeout }
  t.after(() => { delete globalThis.window })

  gtm.gtmEvent({ event: 'view_item' })
  // повторные таймеры создаются внутри tick — идём шагами по 200 мс
  for (let i = 0; i < 30; i += 1) t.mock.timers.tick(200)
  window.gtag = () => assert.fail('event must not be sent after the wait window')
  for (let i = 0; i < 30; i += 1) t.mock.timers.tick(200)
})

