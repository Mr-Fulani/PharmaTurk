/**
 * Централизованные константы сайта — название и URL.
 * Использовать во всех <title> и SEO вместо хардкода 'Turk-Export' или 'Mudaroba'.
 */
export const SITE_NAME = process.env.NEXT_PUBLIC_SITE_NAME || 'Mudaroba'
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || 'https://mudaroba.com').replace(/\/$/, '')

/** Заголовок страницы с « — Mudaroba», без дубля, если CMS уже добавила название сайта. */
export function withSiteName(title: string | null | undefined): string {
  const clean = (title || '').trim()
  if (!clean) return SITE_NAME
  if (clean.toLowerCase().includes(SITE_NAME.toLowerCase())) return clean
  return `${clean} — ${SITE_NAME}`
}
