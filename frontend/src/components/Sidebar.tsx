import { useState } from 'react'
import { useTranslation } from 'next-i18next'

interface SidebarProps {
  categories?: Array<{ id: number; name: string; slug: string; count?: number }>
  brands?: Array<{ id: number; name: string; count?: number }>
  onCategoryChange?: (categoryId: number | null) => void
  onBrandChange?: (brandId: number | null) => void
  onPriceChange?: (min: number | null, max: number | null) => void
  onSortChange?: (sort: string) => void
  onAvailabilityChange?: (inStock: boolean) => void
  selectedCategory?: number | null
  selectedBrand?: number | null
  priceRange?: { min: number | null; max: number | null }
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
  onPriceChange,
  onSortChange,
  onAvailabilityChange,
  selectedCategory,
  selectedBrand,
  priceRange = { min: null, max: null },
  sortBy = 'name_asc',
  inStockOnly = false,
  isOpen = true,
  onToggle
}: SidebarProps) {
  const { t } = useTranslation('common')
  const [showAllCategories, setShowAllCategories] = useState(false)
  const [showAllBrands, setShowAllBrands] = useState(false)
  const [priceMin, setPriceMin] = useState(priceRange.min?.toString() || '')
  const [priceMax, setPriceMax] = useState(priceRange.max?.toString() || '')

  const displayedCategories = showAllCategories ? categories : categories.slice(0, 8)
  const displayedBrands = showAllBrands ? brands : brands.slice(0, 8)

  const handlePriceApply = () => {
    const min = priceMin ? parseFloat(priceMin) : null
    const max = priceMax ? parseFloat(priceMax) : null
    onPriceChange?.(min, max)
  }

  const sortOptions = [
    { value: 'name_asc', label: t('sidebar_sort_name_asc') },
    { value: 'name_desc', label: t('sidebar_sort_name_desc') },
    { value: 'price_asc', label: t('sidebar_sort_price_asc') },
    { value: 'price_desc', label: t('sidebar_sort_price_desc') }
  ]

  return (
    <aside className={`${isOpen ? 'translate-x-0' : '-translate-x-full'} fixed md:relative inset-y-0 left-0 z-50 w-64 bg-white border-r border-gray-200 p-6 space-y-8 transition-transform duration-300 ease-in-out md:translate-x-0`}>
      {/* Mobile overlay */}
      {isOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-40 md:hidden" onClick={onToggle} />
      )}
      
      {/* Mobile close button */}
      <button
        onClick={onToggle}
        className="absolute top-4 right-4 md:hidden text-gray-500 hover:text-gray-700"
      >
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
      {/* Категории */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">{t('sidebar_categories')}</h3>
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {displayedCategories.map((category) => (
            <button
              key={category.id}
              onClick={() => onCategoryChange?.(selectedCategory === category.id ? null : category.id)}
              className={`w-full text-left px-3 py-2 rounded-md transition-colors duration-200 ${
                selectedCategory === category.id
                  ? 'bg-violet-100 text-violet-700 border border-violet-200'
                  : 'text-gray-700 hover:bg-violet-50 hover:text-violet-700'
              }`}
            >
              <div className="flex justify-between items-center">
                <span className="truncate">{category.name}</span>
                {category.count && (
                  <span className="text-xs text-gray-500 ml-2">({category.count})</span>
                )}
              </div>
            </button>
          ))}
        </div>
        {categories.length > 8 && (
          <button
            onClick={() => setShowAllCategories(!showAllCategories)}
            className="mt-3 text-sm text-violet-600 hover:text-violet-800 transition-colors duration-200"
          >
            {showAllCategories ? t('sidebar_show_less') : t('sidebar_show_more')}
          </button>
        )}
      </div>

      {/* Бренды */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">{t('sidebar_brands')}</h3>
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {displayedBrands.map((brand) => (
            <button
              key={brand.id}
              onClick={() => onBrandChange?.(selectedBrand === brand.id ? null : brand.id)}
              className={`w-full text-left px-3 py-2 rounded-md transition-colors duration-200 ${
                selectedBrand === brand.id
                  ? 'bg-violet-100 text-violet-700 border border-violet-200'
                  : 'text-gray-700 hover:bg-violet-50 hover:text-violet-700'
              }`}
            >
              <div className="flex justify-between items-center">
                <span className="truncate">{brand.name}</span>
                {brand.count && (
                  <span className="text-xs text-gray-500 ml-2">({brand.count})</span>
                )}
              </div>
            </button>
          ))}
        </div>
        {brands.length > 8 && (
          <button
            onClick={() => setShowAllBrands(!showAllBrands)}
            className="mt-3 text-sm text-violet-600 hover:text-violet-800 transition-colors duration-200"
          >
            {showAllBrands ? t('sidebar_show_less') : t('sidebar_show_more')}
          </button>
        )}
      </div>

      {/* Фильтры */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">{t('sidebar_filters')}</h3>
        
        {/* Диапазон цен */}
        <div className="mb-6">
          <h4 className="text-sm font-medium text-gray-700 mb-3">{t('sidebar_price_range')}</h4>
          <div className="space-y-3">
            <div>
              <label className="block text-xs text-gray-600 mb-1">{t('sidebar_price_min')}</label>
              <input
                type="number"
                value={priceMin}
                onChange={(e) => setPriceMin(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent"
                placeholder="0"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">{t('sidebar_price_max')}</label>
              <input
                type="number"
                value={priceMax}
                onChange={(e) => setPriceMax(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent"
                placeholder="∞"
              />
            </div>
            <button
              onClick={handlePriceApply}
              className="w-full px-4 py-2 bg-violet-600 text-white text-sm font-medium rounded-md hover:bg-violet-700 transition-colors duration-200"
            >
              Применить
            </button>
          </div>
        </div>

        {/* Сортировка */}
        <div className="mb-6">
          <h4 className="text-sm font-medium text-gray-700 mb-3">{t('sidebar_sort_by')}</h4>
          <div className="space-y-2">
            {sortOptions.map((option) => (
              <button
                key={option.value}
                onClick={() => onSortChange?.(option.value)}
                className={`w-full text-left px-3 py-2 rounded-md text-sm transition-colors duration-200 ${
                  sortBy === option.value
                    ? 'bg-violet-100 text-violet-700 border border-violet-200'
                    : 'text-gray-700 hover:bg-violet-50 hover:text-violet-700'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        {/* Наличие */}
        <div>
          <h4 className="text-sm font-medium text-gray-700 mb-3">{t('sidebar_availability')}</h4>
          <label className="flex items-center space-x-3 cursor-pointer">
            <input
              type="checkbox"
              checked={inStockOnly}
              onChange={(e) => onAvailabilityChange?.(e.target.checked)}
              className="w-4 h-4 text-violet-600 border-gray-300 rounded focus:ring-violet-500"
            />
            <span className="text-sm text-gray-700">{t('sidebar_in_stock')}</span>
          </label>
        </div>
      </div>
    </aside>
  )
}


