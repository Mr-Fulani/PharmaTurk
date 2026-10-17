import assert from 'node:assert/strict'
import test from 'node:test'

import { appendSentenceIfShort, limitTitle, truncateAtWord } from './seoText.js'

test('short text is returned as is with collapsed whitespace', () => {
  assert.equal(truncateAtWord('  Аспирин   500  ', 200), 'Аспирин 500')
})

test('long text is cut at the last whole word with ellipsis', () => {
  const result = truncateAtWord('Успейте приобрести модели из лайкры и плащевой ткани', 30)
  assert.equal(result, 'Успейте приобрести модели из…')
  assert.ok(result.length <= 30)
})

test('whole last word right at the limit is kept', () => {
  assert.equal(truncateAtWord('abc def ghi', 8), 'abc def…')
})

test('trailing punctuation before ellipsis is dropped', () => {
  assert.equal(truncateAtWord('Буркини для бассейна, удлинённая модель', 24), 'Буркини для бассейна…')
})

test('one huge token is hard-cut instead of collapsing to nothing', () => {
  const result = truncateAtWord(`a ${'x'.repeat(50)}`, 20)
  assert.equal(result.length, 20)
  assert.ok(result.endsWith('…'))
})

test('title keeps category and site suffix and shortens only the name', () => {
  const name = 'Успейте приобрести по очень выгодной цене модели из лайкры и из плащевой ткани для бассейна'
  const result = limitTitle(`${name} | Mudaroba`, 70)
  assert.ok(result.length <= 70)
  assert.ok(result.endsWith('… | Mudaroba'))
  assert.equal(limitTitle(`${name} | Буркини | Mudaroba`, 70).endsWith('… | Буркини | Mudaroba'), true)
})

test('short title is untouched', () => {
  assert.equal(limitTitle('Аспирин | Медикаменты | Mudaroba', 70), 'Аспирин | Медикаменты | Mudaroba')
})

test('short brand description gets the template as a separate sentence', () => {
  const suffix = 'Adidas из Турции с доставкой.'
  assert.equal(appendSentenceIfShort('Немецкий спортивный бренд.', suffix), 'Немецкий спортивный бренд. Adidas из Турции с доставкой.')
  assert.equal(appendSentenceIfShort('Spor markası', suffix), 'Spor markası. Adidas из Турции с доставкой.')
  assert.equal(appendSentenceIfShort('', suffix), suffix)
  const long = 'x '.repeat(40).trim()
  assert.equal(appendSentenceIfShort(long, suffix), long)
})
