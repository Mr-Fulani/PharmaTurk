import { useState } from 'react'
import { useTranslation } from 'next-i18next'

interface SidebarProps {
  categories?: Array<{ id: number; name: string; slug: string; count?: number }>
  brands?: Array<{ id: number; name: string; count?: number }>
  onCategoryChange?: (categoryId: number | null) => void
  onBrandChange?: (brandId: number | null) => void
  onSortChange?: (sort: string) => void
  onAvailabilityChange?: (inStock: boolean) => void
  selectedCategory?: number | null
  selectedBrand?: number | null
  sortBy?: string
  inStockOnly?: boolean
  isOpen?: boolean
  onToggle?: () => void
}

export default function Sidebar({
  categories = [],
  brands = [],
  onCategoryChange,
  onBrandChange,
  onSortChange,
  onAvailabilityChange,
  selectedCategory,
  selectedBrand,
  sortBy = 'name_asc',
  inStockOnly = false,
  isOpen = true,
  onToggle
}: SidebarProps) {
  const { t } = useTranslation('common')
  const [showAllCategories, setShowAllCategories] = useState(false)
  const [showAllBrands, setShowAllBrands] = useState(false)

  const displayedCategories = showAllCategories ? categories : categories.slice(0, 8)
  const displayedBrands = showAllBrands ? brands : brands.slice(0, 8)

  const sortOptions = [
    { value: 'name_asc', label: t('sidebar_sort_name_asc') },
    { value: 'name_desc', label: t('sidebar_sort_name_desc') },
    { value: 'price_asc', label: t('sidebar_sort_price_asc') },
    { value: 'price_desc', label: t('sidebar_sort_price_desc') }
  ]

  return (
    <aside className={`${isOpen ? 'translate-x-0' : '-translate-x-full'} fixed md:sticky md:top-6 left-0 z-[5] w-64 bg-[var(--surface)] text-main border border-[var(--border)] rounded-2xl shadow-[0_20px_60px_-20px_rgba(255,255,255,0.65),0_20px_50px_-18px_rgba(109,40,217,0.45)] p-4 space-y-6 transition-transform duration-300 ease-in-out md:translate-x-0 max-h-[calc(100vh-2rem)] overflow-y-auto dark:bg-white/95 dark:text-gray-900 dark:border-gray-200`}>
      {/* Mobile overlay */}
      {isOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-40 md:hidden" onClick={onToggle} />
      )}
      
      {/* Mobile close button */}
      <button
        onClick={onToggle}
        className="absolute top-4 right-4 md:hidden text-main/70 hover:text-main dark:text-gray-500 dark:hover:text-gray-700"
      >
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
      
      {/* Категории */}
      <div>
        <h3 className="text-base font-semibold text-main mb-3 dark:text-gray-900">{t('sidebar_categories')}</h3>
        <div className="space-y-1 max-h-48 overflow-y-auto">
          {displayedCategories.map((category) => (
            <button
              key={category.id}
              onClick={() => onCategoryChange?.(selectedCategory === category.id ? null : category.id)}
            className={`w-full text-left px-2 py-1.5 rounded-lg text-sm transition-colors duration-200 ${
                selectedCategory === category.id
                  ? 'bg-violet-100 text-violet-700 border border-violet-200'
                  : 'text-main/80 hover:bg-violet-50 hover:text-violet-700 dark:text-gray-700'
              }`}
            >
              <div className="flex justify-between items-center">
                <span className="truncate">{category.name}</span>
                {category.count && (
                  <span className="text-xs text-main/60 ml-2 dark:text-gray-500">({category.count})</span>
                )}
              </div>
            </button>
          ))}
        </div>
        {categories.length > 8 && (
          <button
            onClick={() => setShowAllCategories(!showAllCategories)}
            className="mt-2 text-xs text-violet-600 hover:text-violet-800 transition-colors duration-200"
          >
            {showAllCategories ? t('sidebar_show_less') : t('sidebar_show_more')}
          </button>
        )}
      </div>

      {/* Бренды */}
      <div>
        <h3 className="text-base font-semibold text-main mb-3 dark:text-gray-900">{t('sidebar_brands')}</h3>
        <div className="space-y-1 max-h-48 overflow-y-auto">
          {displayedBrands.map((brand) => (
            <button
              key={brand.id}
              onClick={() => onBrandChange?.(selectedBrand === brand.id ? null : brand.id)}
            className={`w-full text-left px-2 py-1.5 rounded-lg text-sm transition-colors duration-200 ${
                selectedBrand === brand.id
                  ? 'bg-violet-100 text-violet-700 border border-violet-200'
                  : 'text-main/80 hover:bg-violet-50 hover:text-violet-700 dark:text-gray-700'
              }`}
            >
              <div className="flex justify-between items-center">
                <span className="truncate">{brand.name}</span>
                {brand.count && (
                  <span className="text-xs text-main/60 ml-2 dark:text-gray-500">({brand.count})</span>
                )}
              </div>
            </button>
          ))}
        </div>
        {brands.length > 8 && (
          <button
            onClick={() => setShowAllBrands(!showAllBrands)}
            className="mt-2 text-xs text-violet-600 hover:text-violet-800 transition-colors duration-200"
          >
            {showAllBrands ? t('sidebar_show_less') : t('sidebar_show_more')}
          </button>
        )}
      </div>

      {/* Фильтры */}
      <div>
        <h3 className="text-base font-semibold text-main mb-3 dark:text-gray-900">{t('sidebar_filters')}</h3>
        
        {/* Сортировка */}
        <div className="mb-4">
          <h4 className="text-sm font-medium text-main mb-2 dark:text-gray-800">{t('sidebar_sort_by')}</h4>
          <div className="space-y-1">
            {sortOptions.map((option) => (
              <button
                key={option.value}
                onClick={() => onSortChange?.(option.value)}
                className={`w-full text-left px-2 py-1.5 rounded-lg text-sm transition-colors duration-200 ${
                  sortBy === option.value
                    ? 'bg-violet-100 text-violet-700 border border-violet-200'
                    : 'text-main/80 hover:bg-violet-50 hover:text-violet-700 dark:text-gray-700'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        {/* Наличие */}
        <div>
          <h4 className="text-sm font-medium text-main mb-2 dark:text-gray-800">{t('sidebar_availability')}</h4>
          <label className="flex items-center space-x-2 cursor-pointer">
            <input
              type="checkbox"
              checked={inStockOnly}
              onChange={(e) => onAvailabilityChange?.(e.target.checked)}
              className="w-4 h-4 text-violet-600 border-gray-300 rounded focus:ring-violet-500"
            />
            <span className="text-sm text-main dark:text-gray-800">{t('sidebar_in_stock')}</span>
          </label>
        </div>
      </div>
    </aside>
  )
}


