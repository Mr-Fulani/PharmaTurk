import Link from 'next/link'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import { NAV_SECTIONS, currentNavSection } from '../lib/sectionNav'

const LINK =
  'whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-medium text-[var(--nav-text)] transition-colors duration-200 hover:border-[var(--nav-accent)] hover:text-[var(--nav-text)]'

/**
 * Строка разделов под шапкой. Идёт в потоке страницы (не закреплена): высота
 * закреплённой шапки и отступ под неё остаются прежними. Отступ под шапку чуть
 * больше её высоты, поэтому фон строки заведён на 12 px под шапку (-mt-3 pt-3) —
 * иначе между ними видна полоска фона страницы. Ссылки — <Link>, это
 * ещё и перелинковка разделов с каждой страницы (DEVELOPMENT_RULES §1.7).
 */
export default function SectionNav() {
  const { t } = useTranslation('common')
  const router = useRouter()
  const current = currentNavSection(router.pathname, router.query)

  return (
    <nav
      aria-label={t('section_nav_label', 'Разделы каталога')}
      className="relative z-10 -mt-3 bg-[var(--nav-bg)] pt-3 text-[var(--nav-text)]"
    >
      <div
        className="mx-auto flex max-w-6xl items-stretch overflow-x-auto px-0 sm:px-3 [&::-webkit-scrollbar]:hidden"
        style={{ scrollbarWidth: 'none' }}
      >
        {NAV_SECTIONS.map((section) => (
          <Link
            key={section.slug}
            href={`/categories/${section.slug}`}
            aria-current={current === section.slug ? 'page' : undefined}
            className={`${LINK} ${current === section.slug ? 'border-[var(--nav-accent)]' : 'border-transparent'}`}
          >
            {t(section.labelKey, section.label)}
          </Link>
        ))}
        <Link href="/categories" className={`${LINK} border-transparent`}>
          {t('section_nav_all', 'Все разделы')}
        </Link>
        <span className="flex-1" aria-hidden="true" />
        <Link href="/how-to-order-medicines" className={`${LINK} hidden border-transparent opacity-80 hover:opacity-100 xl:block`}>
          {t('footer_how_to_order', 'Как заказать')}
        </Link>
      </div>
    </nav>
  )
}
