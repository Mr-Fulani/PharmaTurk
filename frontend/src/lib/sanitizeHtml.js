import DOMPurify from 'isomorphic-dompurify'

const RICH_TEXT_TAGS = [
  'a', 'b', 'blockquote', 'br', 'code', 'del', 'div', 'em', 'h1', 'h2', 'h3',
  'h4', 'h5', 'h6', 'hr', 'i', 'li', 'ol', 'p', 'pre', 's', 'span', 'strong',
  'table', 'tbody', 'td', 'th', 'thead', 'tr', 'u', 'ul',
]

const RICH_TEXT_ATTRIBUTES = [
  'class', 'colspan', 'href', 'rel', 'rowspan', 'title',
]

/**
 * Sanitize CMS, importer and AI supplied markup identically during SSR and in
 * the browser. Images, embeds, forms, inline CSS and event attributes are
 * intentionally excluded from rich text; product media has dedicated fields.
 */
export function sanitizeRichHtml(value) {
  if (typeof value !== 'string' || !value) return ''
  return DOMPurify.sanitize(value, {
    ALLOWED_TAGS: RICH_TEXT_TAGS,
    ALLOWED_ATTR: RICH_TEXT_ATTRIBUTES,
    ALLOW_DATA_ATTR: false,
    ALLOW_ARIA_ATTR: false,
  })
}

/** Escape characters which can terminate an HTML script element in JSON-LD. */
export function safeJsonLd(value) {
  return JSON.stringify(value)
    .replace(/</g, '\\u003c')
    .replace(/>/g, '\\u003e')
    .replace(/&/g, '\\u0026')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029')
}

/** Encode an untrusted scalar before interpolating it into an HTML document. */
export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;',
  })[character])
}
