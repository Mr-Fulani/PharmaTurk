import test from 'node:test'
import assert from 'node:assert/strict'

import { sanitizeNextPath, buildAuthRedirectQuery } from './authRedirect.js'

test('sanitizeNextPath keeps safe internal path with query', () => {
  assert.equal(
    sanitizeNextPath('/testimonials?action=add'),
    '/testimonials?action=add'
  )
})

test('sanitizeNextPath rejects absolute external-looking path', () => {
  assert.equal(sanitizeNextPath('//evil.example.com'), null)
})

test('sanitizeNextPath rejects non-string values', () => {
  assert.equal(sanitizeNextPath(['bad']), null)
})

test('buildAuthRedirectQuery returns next query for valid path', () => {
  assert.deepEqual(
    buildAuthRedirectQuery('/testimonials?action=add'),
    { next: '/testimonials?action=add' }
  )
})

test('buildAuthRedirectQuery returns empty object for unsafe path', () => {
  assert.deepEqual(buildAuthRedirectQuery('https://evil.example.com'), {})
})
