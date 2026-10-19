/**
 * JSON-LD страницы «Как заказать»: FAQPage по видимым вопросам и BreadcrumbList.
 * Ссылки строятся с учётом локали (ru — без префикса, en — /en).
 */
export function buildHowToOrderSchemas({ siteUrl, localePrefix, faqs, breadcrumbs }) {
  const base = `${siteUrl}${localePrefix}`
  return [
    {
      '@context': 'https://schema.org',
      '@type': 'FAQPage',
      mainEntity: faqs.map(({ q, a }) => ({
        '@type': 'Question',
        name: q,
        acceptedAnswer: { '@type': 'Answer', text: a },
      })),
    },
    {
      '@context': 'https://schema.org',
      '@type': 'BreadcrumbList',
      itemListElement: breadcrumbs.map((item, idx) => ({
        '@type': 'ListItem',
        position: idx + 1,
        name: item.label,
        item: item.href === '/' ? base :`${base}${item.href}`,
      })),
    },
  ]
}
