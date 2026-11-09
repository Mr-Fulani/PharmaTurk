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

// Сколько форм перечислять в ответе «В каких формах выпускается…»; остальные — «и ещё N»
const FAQ_FORMS_LIMIT = 10

/**
 * Вопросы и ответы страницы препарата (ТЗ «SEO и видимость в ИИ-поиске», задача 4).
 * Один массив и для видимого блока, и для FAQPage — текст совпадает слово в слово.
 * `link` — ссылка в конце ответа; в разметке её подпись идёт продолжением ответа (faqAnswerText).
 * `t` — функция перевода next-i18next (ключ, фолбэк, параметры).
 *
 * TODO(owner): вопросы про рецепт и правила ввоза не добавлены — нужны ответы владельца.
 */
export function buildDrugGroupFaq({ heading, priceText, forms, t }) {
  const names = (forms || []).map((form) => String(form?.name || '').trim()).filter(Boolean)
  const shown = names.slice(0, FAQ_FORMS_LIMIT).join('; ')
  const rest = names.length - Math.min(names.length, FAQ_FORMS_LIMIT)
  const faq = [
    {
      question: t('drug_faq_price_q', 'Сколько стоит {{heading}}?', { heading }),
      answer: priceText
        ? t('drug_faq_price_a', 'Цена {{heading}} в Турции — от {{price}}. Это справочная розничная цена турецких аптек, она может меняться. Итоговую стоимость с доставкой менеджер называет в расчёте после заявки.', { heading, price: priceText })
        : t('drug_faq_price_a_none', 'Цена {{heading}} — по запросу: после заявки менеджер проверит наличие и назовёт стоимость с доставкой.', { heading }),
    },
  ]
  if (shown) {
    faq.push({
      question: t('drug_faq_forms_q', 'В каких формах выпускается {{heading}}?', { heading }),
      answer: rest > 0
        ? t('drug_faq_forms_a_more', 'Формы и дозировки на сайте: {{forms}} и ещё {{rest}}.', { forms: shown, rest })
        : t('drug_faq_forms_a', 'Формы и дозировки на сайте: {{forms}}.', { forms: shown }),
    })
  }
  faq.push(
    {
      question: t('drug_faq_delivery_q', 'Сколько идёт доставка?'),
      answer: t('drug_faq_delivery_a', 'Доставка из Турции: авиа 3–7, наземная 7–14, морем 20–45 дней. Точный срок менеджер называет в расчёте.'),
    },
    {
      question: t('drug_faq_order_q', 'Как заказать {{heading}}?', { heading }),
      answer: t('drug_faq_order_a', 'Сайт не продаёт лекарства. Нажмите «В заявку» на странице нужной формы или отправьте название менеджеру. Менеджер проверит наличие, рассчитает стоимость с доставкой и согласует оплату — платить нужно только после расчёта.'),
      link: {
        href: '/how-to-order-medicines',
        label: t('drug_faq_order_link', 'Подробнее — на странице «Как заказать лекарства из Турции».'),
      },
    },
  )
  return faq
}

/** Полный текст ответа, как его видит читатель: ответ и подпись ссылки. */
export function faqAnswerText(item) {
  return item.link ? `${item.answer} ${item.link.label}` : item.answer
}

/**
 * JSON-LD страницы препарата: BreadcrumbList и FAQPage по видимым вопросам. Drug не выводится: без Offer, отзывов и рейтинга
 * Google считает его товаром с ошибкой (как 222 карточки лекарств, 25.10.2026), а цену в разметку
 * лекарств не ставим (см. canPublishSchemaOffer, shouldPublishProductSchema).
 */
export function buildDrugGroupSchemas({ siteUrl, localePrefix, breadcrumbs, faq = [] }) {
  const base = `${siteUrl}${localePrefix}`
  const schemas = [
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
  if (faq.length > 0) {
    schemas.push({
      '@context': 'https://schema.org',
      '@type': 'FAQPage',
      mainEntity: faq.map((item) => ({
        '@type': 'Question',
        name: item.question,
        acceptedAnswer: { '@type': 'Answer', text: faqAnswerText(item) },
      })),
    })
  }
  return schemas
}
