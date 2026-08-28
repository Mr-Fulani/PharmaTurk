import test from 'node:test'
import assert from 'node:assert/strict'

import {
  appendWhatsappText,
  normalizeMedicineSlug,
  shouldPollMedicineMarketCheck,
  startMedicineMarketCheckSingleFlight,
} from './medicineMarketCheck.js'

test('medicine check accepts only a catalog slug', () => {
  assert.equal(normalizeMedicineSlug('lasirin-20-mg-tablet'), 'lasirin-20-mg-tablet')
  assert.equal(normalizeMedicineSlug('bad/path'), '')
  assert.equal(normalizeMedicineSlug(['valid-slug', 'ignored']), 'valid-slug')
})

test('only active market checks are polled', () => {
  assert.equal(shouldPollMedicineMarketCheck('pending'), true)
  assert.equal(shouldPollMedicineMarketCheck('running'), true)
  assert.equal(shouldPollMedicineMarketCheck('succeeded'), false)
  assert.equal(shouldPollMedicineMarketCheck('source_unavailable'), false)
})

test('Strict Mode style concurrent starts share one POST promise', async () => {
  let calls = 0
  let resolveRequest
  const response = new Promise((resolve) => {
    resolveRequest = resolve
  })
  const starter = () => {
    calls += 1
    return response
  }

  const first = startMedicineMarketCheckSingleFlight('lasirin', starter)
  const second = startMedicineMarketCheckSingleFlight('lasirin', starter)
  resolveRequest({ data: { status: 'pending' } })

  assert.equal(await first, await second)
  assert.equal(calls, 1)
})

test('whatsapp helper preserves existing provider parameters', () => {
  const url = appendWhatsappText('https://wa.me/900000000?source=site', 'Цена 10 TRY')
  const parsed = new URL(url)
  assert.equal(parsed.searchParams.get('source'), 'site')
  assert.equal(parsed.searchParams.get('text'), 'Цена 10 TRY')
})
