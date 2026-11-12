import Link from 'next/link'
import { useTranslation } from 'next-i18next'
import type { ReactNode } from 'react'

export interface CategoryTile {
  id: number | string
  href: string
  name: string
  /** Число товаров, уже отформатированное */
  count: string
  /** Карточка раздела из админки (картинка или ролик) */
  media: ReactNode
}

export interface CategoryLink {
  href: string
  name: string
}

function Tile({ tile, fill = false }: { tile: CategoryTile; fill?: boolean }) {
  return (
    <Link
      href={tile.href}
      className="group flex flex-col overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--card-bg)] transition-colors duration-200 hover:border-[var(--accent)]"
    >
      <div className={`relative aspect-[4/3] overflow-hidden bg-gray-100 ${fill ? 'lg:aspect-auto lg:min-h-[120px] lg:flex-1' : ''}`}>{tile.media}</div>
      {/* В узкой плитке (четыре в ряд) длинное название и число в одну строку не помещаются — число уходит под название. */}
      <div className={`flex items-baseline justify-between gap-2 px-3 py-2.5 ${fill ? '' : 'lg:flex-col lg:justify-start lg:gap-0.5'}`}>
        <h3 className="min-w-0 text-sm font-semibold leading-tight text-[var(--text-strong)] group-hover:text-[var(--accent)]">{tile.name}</h3>
        <span className="flex-none text-xs tabular-nums text-main opacity-70">{tile.count}</span>
      </div>
    </Link>
  )
}

/**
 * Разделы на главной двумя блоками: «Аптека» (лекарства и БАДы) и «Гардероб и дом»
 * (всё остальное). Плитки одного размера, подпись под картинкой; картинки — карточки
 * разделов из админки. Разделы, которым не хватило плитки, идут строкой ссылок:
 * пустые разделы не скрываются.
 */
export default function HomeCategoryWorlds({ pharmacy, goods, others }: { pharmacy: CategoryTile[]; goods: CategoryTile[]; others: CategoryLink[] }) {
  const { t } = useTranslation('common')

  // Разделы не загрузились — пустые рамки не показываем.
  if (pharmacy.length === 0 && goods.length === 0) return null

  return (
    <section className={`mb-12 grid grid-cols-1 gap-4 lg:gap-6 ${pharmacy.length > 0 ? 'lg:grid-cols-[5fr_7fr]' : ''}`}>
      {pharmacy.length > 0 && (
        <div className="flex flex-col rounded-2xl bg-[var(--surface)] p-4 md:p-6">
          <h2 className="text-2xl font-bold text-[var(--text-strong)] md:text-3xl">{t('home_world_pharmacy_title', 'Аптека')}</h2>
          <p className="mt-1 text-sm text-main opacity-80">{t('home_world_pharmacy_text', 'Лекарства и БАДы из турецких аптек')}</p>
          {/* На широком экране плитки аптеки идут друг под другом и растягиваются на высоту соседнего блока. */}
          <div className="mt-4 grid grid-cols-2 gap-3 lg:flex-1 lg:auto-rows-fr lg:grid-cols-1">
            {pharmacy.map((tile) => <Tile key={tile.id} tile={tile} fill />)}
          </div>
          <p className="mt-4 text-[13px] leading-snug text-main opacity-80">
            {t('home_world_pharmacy_note', 'Цены на лекарства справочные. Наличие и итог с доставкой проверит менеджер.')}
          </p>
        </div>
      )}
      <div className="rounded-2xl border border-[var(--border)] p-4 md:p-6">
        <h2 className="text-2xl font-bold text-[var(--text-strong)] md:text-3xl">{t('home_world_goods_title', 'Гардероб и дом')}</h2>
        <p className="mt-1 text-sm text-main opacity-80">{t('home_world_goods_text', 'Одежда, обувь и товары для дома турецких и мировых брендов')}</p>
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {goods.map((tile) => <Tile key={tile.id} tile={tile} />)}
        </div>
        {others.length > 0 && (
          <p className="mt-4 text-sm leading-relaxed text-main">
            <span className="opacity-80">{t('home_world_more', 'Другие разделы')}: </span>
            {others.map((link, index) => (
              <span key={link.href}>
                {index > 0 && ' · '}
                <Link href={link.href} className="underline decoration-[var(--border)] underline-offset-4 hover:text-[var(--accent)]">{link.name}</Link>
              </span>
            ))}
          </p>
        )}
        <div className="mt-5">
          <Link
            href="/categories"
            className="inline-flex items-center rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white shadow transition-colors hover:bg-[var(--accent-strong)] hover:text-white"
          >
            {t('all_categories', 'Все категории')}
          </Link>
        </div>
      </div>
    </section>
  )
}
