import Link from 'next/link'
import { useTranslation } from 'next-i18next'

export interface RelatedProductLink {
  name: string
  path: string
}

/**
 * Текстовые ссылки на соседние товары категории, отдаются в SSR-HTML
 * (related_links из resolve) — перелинковка для поисковиков без клиентской загрузки.
 */
export default function RelatedProductLinks({ links }: { links: RelatedProductLink[] }) {
  const { t } = useTranslation('common')
  if (!links.length) return null
  return (
    <nav className="mt-8" aria-label={t('related_product_links_title', 'Ещё в этой категории')}>
      <h2 className="text-lg font-semibold text-[var(--text-strong)] mb-3">
        {t('related_product_links_title', 'Ещё в этой категории')}
      </h2>
      <ul className="grid gap-x-6 gap-y-2 sm:grid-cols-2 text-sm">
        {links.map((link) => (
          <li key={link.path} className="truncate">
            <Link href={link.path} className="text-main hover:text-[var(--accent)] transition-colors">
              {link.name}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  )
}
