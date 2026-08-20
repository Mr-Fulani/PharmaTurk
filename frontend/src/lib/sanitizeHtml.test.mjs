import test from 'node:test'
import assert from 'node:assert/strict'

import { escapeHtml, safeJsonLd, sanitizeRichHtml } from './sanitizeHtml.js'

test('sanitizeRichHtml removes executable and active content', () => {
  const dirty = [
    '<p onclick="alert(1)">Safe <strong>text</strong></p>',
    '<script>alert(2)</script>',
    '<img src=x onerror="alert(3)">',
    '<a href="javascript:alert(4)" style="display:none">bad link</a>',
  ].join('')

  const clean = sanitizeRichHtml(dirty)

  assert.match(clean, /<p>Safe <strong>text<\/strong><\/p>/)
  assert.doesNotMatch(clean, /onclick|onerror|<script|<img|javascript:|style=/i)
})

test('safeJsonLd cannot terminate the containing script element', () => {
  const encoded = safeJsonLd({ name: '</script><script>alert(1)</script>' })

  assert.doesNotMatch(encoded, /<|>/)
  assert.match(encoded, /\\u003c\/script\\u003e/)
})

test('escapeHtml protects generated receipt documents', () => {
  assert.equal(
    escapeHtml(`<img src=x onerror="alert('x')"> &`),
    '&lt;img src=x onerror=&quot;alert(&#039;x&#039;)&quot;&gt; &amp;',
  )
})
