export type FooterLocale = 'en' | 'ru'

export function normalizeFooterLocale(language?: string | null): FooterLocale {
  const baseLanguage = (language || '').trim().toLowerCase().replace('_', '-').split('-')[0]
  return baseLanguage === 'en' ? 'en' : 'ru'
}

export function buildFooterPagesParams(language?: string | null): { lang: FooterLocale } {
  return { lang: normalizeFooterLocale(language) }
}
