/**
 * Страница препарата /drugs/<slug>: бренд и все его формы (SEO-план медикаментов, пункт 3).
 * Тексты по языкам приходят из /api/catalog/medicine-groups/<slug>; перевода на языке
 * страницы нет — шаблон, а не текст другого языка (DEVELOPMENT_RULES §1.8).
 */

/** «Мажезик (MAJEZIK)»; если название совпадает с латиницей — только «MAJEZIK». */
export function drugGroupHeading({ name, latin }) {
  const local = String(name || '').trim()
  const brand = String(latin || '').trim()
  if (!local || local.toLowerCase() === brand.toLowerCase()) return brand || local
  return `${local} (${brand})`
}

/** Перевод препарата на языке страницы или пустой объект. */
export function drugGroupTranslation(group, locale) {
  const list = Array.isArray(group?.translations) ? group.translations : []
  return list.find((item) => item.locale === locale) || {}
}

/** Абзацы через пустую строку (как seo_text). */
export function splitParagraphs(text) {
  return String(text || '')
    .split(/\n\s*\n/)
    .map((part) => part.replace(/\s+/g, ' ').trim())
    .filter(Boolean)
}

/** «2026-10-24T…» → «24.10.2026» без часового пояса: одинаково на сервере и в браузере. */
export function formatIsoDate(value) {
  const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})/)
  return match ? `${match[3]}.${match[2]}.${match[1]}` : ''
}

/** Самая низкая цена среди форм с ценой: { price, currency } или null. */
export function lowestPrice(forms) {
  let best = null
  for (const form of forms || []) {
    const price = Number(form?.price)
    if (!Number.isFinite(price) || price <= 0) continue
    if (!best || price < best.price) best = { price, currency: form.currency || '' }
  }
  return best
}

/** Начало и предложения по порядку, пока помещаются в maxLength (не обрезая на полуслове). */
export function joinSentencesWithin(sentences, maxLength) {
  let text = ''
  for (const sentence of sentences) {
    const clean = String(sentence || '').replace(/\s+/g, ' ').trim()
    if (!clean) continue
    const next = text ? `${text} ${clean}` : clean
    if (next.length > maxLength) {
      if (!text) return clean.slice(0, maxLength)
      continue
    }
    text = next
  }
  return text
}

/**
 * JSON-LD страницы препарата: BreadcrumbList. Drug не выводится: без Offer, отзывов и рейтинга
 * Google считает его товаром с ошибкой (как 222 карточки лекарств, 25.10.2026), а цену в разметку
 * лекарств не ставим (см. canPublishSchemaOffer, shouldPublishProductSchema).
 */
export function buildDrugGroupSchemas({ siteUrl, localePrefix, breadcrumbs }) {
  const base = `${siteUrl}${localePrefix}`
  return [
    {
      '@context': 'https://schema.org',
      '@type': 'BreadcrumbList',
      itemListElement: breadcrumbs.map((item, idx) => ({
        '@type': 'ListItem',
        position: idx + 1,
        name: item.label,
        item: item.href === '/' ? base : `${base}${item.href}`,
      })),
    },
  ]
}
