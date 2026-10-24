/**
 * Блог: JSON-LD статьи (Article + FAQPage + BreadcrumbList) и плоский текст абзаца.
 * Ссылки строятся с учётом локали (ru — без префикса, en — /en).
 */

/** Части абзаца (строки и ссылки { href, text }) → текст. */
export function partsToText(parts) {
  return (parts || []).map((part) => (typeof part === 'string' ? part : part?.text || '')).join('')
}

/** Все ссылки статьи — для проверки, что они ведут на свои страницы. */
export function articleLinks(article) {
  const links = []
  const collect = (parts) => {
    for (const part of parts || []) {
      if (part && typeof part === 'object' && part.href) links.push(part.href)
    }
  }
  for (const section of article.sections || []) {
    for (const block of section.blocks || []) {
      if (block.type === 'p') collect(block.parts)
      if (block.type === 'ul') block.items.forEach(collect)
      if (block.type === 'table') block.rows.forEach((row) => row.forEach(collect))
    }
  }
  return links
}

/** Весь видимый текст статьи на одном языке: заголовки, абзацы, таблицы, FAQ. */
export function articleText(article) {
  const chunks = [article.title, article.metaTitle, article.description, article.lead]
  for (const section of article.sections || []) {
    chunks.push(section.heading)
    for (const block of section.blocks || []) {
      if (block.type === 'p') chunks.push(partsToText(block.parts))
      if (block.type === 'ul') chunks.push(...block.items.map(partsToText))
      if (block.type === 'table') {
        chunks.push(...(block.head || []))
        for (const row of block.rows) chunks.push(...row.map(partsToText))
      }
    }
  }
  for (const item of article.faq || []) chunks.push(item.q, item.a)
  return chunks.filter(Boolean).join('\n')
}

export function buildFaqSchema(faq) {
  return {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: faq.map(({ q, a }) => ({
      '@type': 'Question',
      name: q,
      acceptedAnswer: { '@type': 'Answer', text: a },
    })),
  }
}

export function buildBreadcrumbSchema({ siteUrl, localePrefix, breadcrumbs }) {
  const base = `${siteUrl}${localePrefix}`
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: breadcrumbs.map((item, idx) => ({
      '@type': 'ListItem',
      position: idx + 1,
      name: item.label,
      item: item.href === '/' ? base : `${base}${item.href}`,
    })),
  }
}

/** Article (автор и издатель — редакция сайта), FAQPage по видимым вопросам, BreadcrumbList. */
export function buildArticleSchemas({ siteUrl, siteName, localePrefix, article, locale, breadcrumbs }) {
  const url = `${siteUrl}${localePrefix}/blog/${article.slug}`
  const schemas = [
    {
      '@context': 'https://schema.org',
      '@type': 'Article',
      headline: article.title,
      description: article.description,
      inLanguage: locale,
      datePublished: article.publishedAt,
      dateModified: article.updatedAt,
      mainEntityOfPage: url,
      url,
      author: { '@type': 'Organization', name: siteName, url: siteUrl },
      publisher: { '@type': 'Organization', name: siteName, logo: { '@type': 'ImageObject', url: `${siteUrl}/logo.svg` } },
    },
    buildBreadcrumbSchema({ siteUrl, localePrefix, breadcrumbs }),
  ]
  if (article.faq?.length) schemas.splice(1, 0, buildFaqSchema(article.faq))
  return schemas
}
