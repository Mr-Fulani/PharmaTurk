import assert from 'node:assert/strict'
import test from 'node:test'

import { formatFitmentPeriod, formatFitmentPower, summarizeModels } from './autoPartFitment.js'

test('период выпуска: закрытый, открытый и пустой', () => {
  assert.equal(formatFitmentPeriod({ year_from: 2012, month_from: 3, year_to: 2018, month_to: 10 }), '03.2012 – 10.2018')
  assert.equal(formatFitmentPeriod({ year_from: 2012, month_from: 7 }), 'с 07.2012')
  assert.equal(formatFitmentPeriod({ year_from: 2012, month_from: 7 }, 'en'), 'from 07.2012')
  assert.equal(formatFitmentPeriod({ year_from: 2005, year_to: 2010 }), '2005 – 2010')
  assert.equal(formatFitmentPeriod({}), '')
})

test('мощность на языке страницы', () => {
  assert.equal(formatFitmentPower({ power_kw: 135, power_hp: 184 }), '135 кВт / 184 л. с.')
  assert.equal(formatFitmentPower({ power_kw: 135, power_hp: 184 }, 'en'), '135 kW / 184 hp')
  assert.equal(formatFitmentPower({ power_kw: null, power_hp: null }), '')
})

test('длинный список моделей сокращается', () => {
  assert.equal(summarizeModels(['Golf', 'Passat']), 'Golf, Passat')
  assert.equal(summarizeModels(['A', 'B', 'C', 'D'], 2), 'A, B и ещё 2')
  assert.equal(summarizeModels(['A', 'B', 'C', 'D'], 2, 'en'), 'A, B and 2 more')
  assert.equal(summarizeModels(null), '')
})
