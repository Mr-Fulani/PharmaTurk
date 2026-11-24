import { useTranslation } from 'next-i18next'
import { SEARCH_SORTS } from '../lib/searchResults'

export type SearchFiltersValue = { type: string; brand: number | null; available: boolean; sort: string }
type Facets = { types: { value: string; count: number }[]; brands: { id: number; name: string; count: number }[] }

// Фильтры и сортировка страницы поиска: разделы найденного плашками, бренд, «в наличии», порядок.
// Цвета — из переменных темы оформления (docs/DESIGN_THEMES.md), строки и кнопки от 44 px.
export default function SearchFilters({
  facets,
  value,
  onChange,
}: {
  facets: Facets
  value: SearchFiltersValue
  onChange: (next: SearchFiltersValue) => void
}) {
  const { t } = useTranslation('common')
  const sortLabels: Record<string, string> = {
    relevance: t('search_sort_relevance', 'По точности'),
    price_asc: t('search_sort_price_asc', 'Сначала дешёвые'),
    price_desc: t('search_sort_price_desc', 'Сначала дорогие'),
    newest: t('search_sort_newest', 'Сначала новые'),
  }
  const chip = (active: boolean) =>
    `min-h-[44px] shrink-0 rounded-full border px-4 text-sm transition-colors ${
      active
        ? 'border-[var(--accent)] bg-[var(--accent)] text-white'
        : 'border-[var(--border)] bg-[var(--surface)] text-[var(--text-strong)] hover:border-[var(--accent)]'
    }`
  const control =
    'min-h-[44px] rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 text-sm text-[var(--text-strong)]'

  return (
    <div className="mt-4 space-y-3" data-testid="search-filters">
      {facets.types.length > 1 || value.type ? (
        <div className="-mx-3 flex gap-2 overflow-x-auto px-3 pb-1 sm:mx-0 sm:flex-wrap sm:px-0" role="group" aria-label={t('search_filter_sections', 'Разделы')}>
          <button type="button" className={chip(!value.type)} aria-pressed={!value.type} onClick={() => onChange({ ...value, type: '' })}>
            {t('section_nav_all', 'Все разделы')}
          </button>
          {facets.types.map((row) => (
            <button
              key={row.value}
              type="button"
              className={chip(value.type === row.value)}
              aria-pressed={value.type === row.value}
              onClick={() => onChange({ ...value, type: value.type === row.value ? '' : row.value })}
            >
              {t(`section_nav_${row.value}`, row.value)} <span className="opacity-70">{row.count}</span>
            </button>
          ))}
        </div>
      ) : null}
      <div className="flex flex-wrap items-center gap-3">
        {facets.brands.length > 1 || value.brand ? (
          <select
            className={control}
            aria-label={t('brand', 'Бренд')}
            value={value.brand ?? ''}
            onChange={(event) => onChange({ ...value, brand: Number(event.target.value) || null })}
          >
            <option value="">{t('all_brands', 'Все бренды')}</option>
            {facets.brands.map((row) => (
              <option key={row.id} value={row.id}>
                {row.name} ({row.count})
              </option>
            ))}
          </select>
        ) : null}
        <label className={`${control} inline-flex cursor-pointer items-center gap-2`}>
          <input
            type="checkbox"
            className="h-4 w-4 accent-[var(--accent)]"
            checked={value.available}
            onChange={(event) => onChange({ ...value, available: event.target.checked })}
          />
          {t('in_stock', 'В наличии')}
        </label>
        <select
          className={`${control} sm:ml-auto`}
          aria-label={t('search_sort_label', 'Сортировка')}
          value={value.sort}
          onChange={(event) => onChange({ ...value, sort: event.target.value })}
        >
          {SEARCH_SORTS.map((sort) => (
            <option key={sort} value={sort}>
              {sortLabels[sort]}
            </option>
          ))}
        </select>
      </div>
    </div>
  )
}
