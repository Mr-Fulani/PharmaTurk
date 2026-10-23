import Link from 'next/link'
import { splitSeoText } from '../lib/seoText'

export interface CategoryLandingLinkGroup {
  title: string
  links: Array<{ href: string; label: string }>
}

interface CategoryLandingBlockProps {
  linkGroups: CategoryLandingLinkGroup[]
  seoText?: string | null
}

/**
 * Низ посадочной страницы каталога: ссылки на разделы и подборки (перелинковка
 * для поисковиков и людей) и SEO-текст из API (seo_text категории или подборки).
 */
export default function CategoryLandingBlock({ linkGroups, seoText }: CategoryLandingBlockProps) {
  const blocks = splitSeoText(seoText || '') as Array<{ kind: 'heading' | 'paragraph'; text: string }>
  const groups = linkGroups.filter((group) => group.links.length > 0)
  if (groups.length === 0 && blocks.length === 0) return null

  return (
    <div className="mt-4 space-y-8">
      {groups.length > 0 && (
        <nav className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4 sm:p-6">
          {groups.map((group) => (
            <div key={group.title} className="mb-5 last:mb-0">
              <h2 className="mb-3 text-lg font-semibold text-main">{group.title}</h2>
              <ul className="flex flex-wrap gap-2">
                {group.links.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className="inline-flex min-h-11 items-center rounded-full border border-[var(--border)] bg-[var(--bg)] px-4 py-2 text-sm text-main transition-colors hover:border-[var(--accent)] hover:text-[var(--accent)]"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
      )}
      {blocks.length > 0 && (
        <section className="max-w-4xl text-main">
          {blocks.map((block, index) =>
            block.kind === 'heading' ? (
              <h2 key={index} className="mb-3 mt-6 text-xl font-semibold first:mt-0">
                {block.text}
              </h2>
            ) : (
              <p key={index} className="mb-4 leading-relaxed">
                {block.text}
              </p>
            )
          )}
        </section>
      )}
    </div>
  )
}
