/**
 * Централизованные константы сайта — название и URL.
 * Использовать во всех <title> и SEO вместо хардкода 'Turk-Export' или 'Mudaroba'.
 */
export const SITE_NAME = process.env.NEXT_PUBLIC_SITE_NAME || 'Mudaroba'
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || 'https://mudaroba.com').replace(/\/$/, '')
