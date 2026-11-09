import test from 'node:test'
import assert from 'node:assert/strict'

import { defaultOgImageAlt, defaultOgImagePath } from './ogImage.js'

test('картинка-превью по языку страницы', () => {
  assert.equal(defaultOgImagePath('ru'), '/og-default.jpg')
  assert.equal(defaultOgImagePath(undefined), '/og-default.jpg')
  assert.equal(defaultOgImagePath('en'), '/og-default-en.jpg')
  assert.match(defaultOgImageAlt('ru'), /из Турции/)
  assert.match(defaultOgImageAlt('en'), /from Turkey/)
})
