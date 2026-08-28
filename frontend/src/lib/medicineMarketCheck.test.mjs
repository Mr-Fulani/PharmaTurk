import test from 'node:test'
import assert from 'node:assert/strict'

import {
  appendWhatsappText,
  buildMedicineConsultMessage,
  buildMedicineHowToOrderHref,
  normalizeMedicineSlug,
  shouldPollMedicineMarketCheck,
  startMedicineMarketCheckSingleFlight,
} from './medicineMarketCheck.js'

test('medicine intent link carries only an encoded catalog slug', () => {
  assert.equal(
    buildMedicineHowToOrderHref('lasirin-20-mg-tablet'),
    '/how-to-order-medicines?medicine=lasirin-20-mg-tablet',
  )
  assert.equal(buildMedicineHowToOrderHref('bad/path'), '/how-to-order-medicines')
  assert.equal(normalizeMedicineSlug(['valid-slug', 'ignored']), 'valid-slug')
})

test('only active market checks are polled', () => {
  assert.equal(shouldPollMedicineMarketCheck('pending'), true)
  assert.equal(shouldPollMedicineMarketCheck('running'), true)
  assert.equal(shouldPollMedicineMarketCheck('succeeded'), false)
  assert.equal(shouldPollMedicineMarketCheck('source_unavailable'), false)
})

test('consult message contains medicine identity and checked reference price', () => {
  const message = buildMedicineConsultMessage(
    { name: 'LASIRIN', dosage_form: 'tablet', volume: '20 шт.' },
    { price: { amount: '125.45', currency: 'TRY' }, last_success_at: '2026-08-28T10:00:00Z' },
    'https://mudaroba.com/product/lasirin',
  )
  assert.match(message, /LASIRIN, tablet, 20 шт\./)
  assert.match(message, /125\.45 TRY/)
  assert.match(message, /2026-08-28/)
  assert.match(message, /https:\/\/mudaroba\.com\/product\/lasirin/)
})

test('consult message follows the current locale', () => {
  const message = buildMedicineConsultMessage(
    { name: 'LASIRIN' },
    { price: { amount: '125.45', currency: 'TRY' } },
    'https://mudaroba.com/en/product/lasirin',
    'en',
  )
  assert.match(message, /^Hello! I need advice/)
  assert.match(message, /Reference price: 125\.45 TRY/)
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
