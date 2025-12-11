import { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'next-i18next'

export interface SidebarTreeItem {
  id: string
  name: string
  slug?: string
  dataId?: number
  count?: number
  type?: 'category' | 'brand' | 'subcategory'
  children?: SidebarTreeItem[]
}

export interface SidebarTreeSection {
  title: string
  items: SidebarTreeItem[]
}

export interface FilterState {
  categories: number[]
  categorySlugs: string[]
  brands: number[]
  brandSlugs: string[]
  subcategories: number[]
  subcategorySlugs: string[]
  priceMin?: number
  priceMax?: number
  inStock: boolean
  sortBy: string
  colors?: string[]
  sizes?: string[]
  shoeTypes?: string[]
  clothingItems?: string[]
  jewelryMaterials?: string[]
  jewelryGender?: string[]
  headwearTypes?: string[]
}

interface Category {
  id: number
  name: string
  slug: string
  children_count?: number
  product_count?: number
}

interface Brand {
  id: number
  name: string
  slug: string
  logo?: string
  product_count?: number
}

interface CategorySidebarProps {
  categories?: Category[]
  brands?: Brand[]
  subcategories?: Category[]
  categoryGroups?: SidebarTreeSection[]
  brandGroups?: SidebarTreeSection[]
  onFilterChange?: (filters: FilterState) => void
  isOpen?: boolean
  onToggle?: () => void
  initialFilters?: FilterState
  showSubcategories?: boolean
  categoryType?: string
}

const toggleArrayValue = <T,>(arr: T[], value: T): T[] =>
  arr.includes(value) ? arr.filter((item) => item !== value) : [...arr, value]

const ensureSlug = (value?: string) => (value ? value.trim().toLowerCase().replace(/\s+/g, '-') : '')

export default function CategorySidebar({
  categories = [],
  brands = [],
  subcategories = [],
  categoryGroups = [],
  brandGroups = [],
  onFilterChange,
  isOpen = true,
  onToggle,
  initialFilters,
  showSubcategories = false,
  categoryType
}: CategorySidebarProps) {
  const { t } = useTranslation('common')
  const defaultFilters: FilterState = {
    categories: [],
    categorySlugs: [],
    brands: [],
    brandSlugs: [],
    subcategories: [],
    subcategorySlugs: [],
    inStock: false,
    sortBy: 'name_asc',
    shoeTypes: [],
    clothingItems: [],
    jewelryMaterials: [],
    jewelryGender: [],
    headwearTypes: [],
  }
  const [filters, setFilters] = useState<FilterState>(initialFilters || defaultFilters)
  
  // Синхронизация с внешними фильтрами
  useEffect(() => {
    if (initialFilters) {
      setFilters(initialFilters)
      // Синхронизируем ценовой диапазон
      setPriceRange({
        min: initialFilters.priceMin?.toString() || '',
        max: initialFilters.priceMax?.toString() || ''
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    initialFilters?.brands?.join(','),
    initialFilters?.categories?.join(','),
    initialFilters?.subcategories?.join(','),
    initialFilters?.inStock,
    initialFilters?.sortBy,
    initialFilters?.priceMin,
    initialFilters?.priceMax
  ])
  
  const [priceRange, setPriceRange] = useState({ 
    min: initialFilters?.priceMin?.toString() || '', 
    max: initialFilters?.priceMax?.toString() || '' 
  })
  const [expandedSections, setExpandedSections] = useState({
    categories: true,
    brands: true,
    subcategories: true,
    price: true,
    filters: true
  })
  const [expandedTreeItems, setExpandedTreeItems] = useState<Record<string, boolean>>({})

  useEffect(() => {
    if (onFilterChange) {
      onFilterChange(filters)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    filters.brands.join(','),
    filters.categories.join(','),
    filters.subcategories.join(','),
    filters.brandSlugs.join(','),
    filters.categorySlugs.join(','),
    filters.subcategorySlugs.join(','),
    filters.priceMin,
    filters.priceMax,
    filters.inStock,
    filters.sortBy
  ])

  const updateFilters = (updater: (prev: FilterState) => FilterState) => {
    setFilters((prev) => updater(prev))
  }

  const toggleCategoryFilter = (categoryId: number, slug?: string) => {
    updateFilters((prev) => ({
      ...prev,
      categories: toggleArrayValue(prev.categories, categoryId),
      categorySlugs: slug ? toggleArrayValue(prev.categorySlugs, slug) : prev.categorySlugs
    }))
  }

  const toggleBrandFilter = (brandId: number, slug?: string) => {
    updateFilters((prev) => ({
      ...prev,
      brands: toggleArrayValue(prev.brands, brandId),
      brandSlugs: slug ? toggleArrayValue(prev.brandSlugs, slug) : prev.brandSlugs
    }))
  }

  const toggleSubcategoryFilter = (subcategoryId: number, slug?: string) => {
    updateFilters((prev) => ({
      ...prev,
      subcategories: toggleArrayValue(prev.subcategories, subcategoryId),
      subcategorySlugs: slug ? toggleArrayValue(prev.subcategorySlugs, slug) : prev.subcategorySlugs
    }))
  }

  const handlePriceChange = () => {
    updateFilters((prev) => ({
      ...prev,
      priceMin: priceRange.min ? Number(priceRange.min) : undefined,
      priceMax: priceRange.max ? Number(priceRange.max) : undefined
    }))
  }

  const clearFilters = () => {
    setFilters({
      categories: [],
      categorySlugs: [],
      brands: [],
      brandSlugs: [],
      subcategories: [],
      subcategorySlugs: [],
      inStock: false,
      sortBy: 'name_asc'
    })
    setPriceRange({ min: '', max: '' })
  }

  const toggleTreeItem = (itemId: string) => {
    setExpandedTreeItems((prev) => ({
      ...prev,
      [itemId]: !prev[itemId]
    }))
  }

  const renderTreeItems = (items: SidebarTreeItem[]) =>
    items.map((item) => {
      const hasChildren = item.children && item.children.length > 0
      const isExpanded = expandedTreeItems[item.id]
      return (
        <div key={item.id} className="space-y-1">
          <button
            type="button"
            className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm font-medium ${
              item.dataId ? 'text-gray-700 hover:text-violet-700 cursor-pointer' : 'text-gray-400 cursor-not-allowed'
            }`}
            onClick={() => {
              if (hasChildren) {
                toggleTreeItem(item.id)
                return
              }
              // Не применяем фильтры для placeholder элементов без dataId
              if (!item.dataId) {
                return
              }
              if (item.type === 'brand') {
                toggleBrandFilter(item.dataId, item.slug || undefined)
                return
              }
              toggleCategoryFilter(item.dataId, item.slug || undefined)
            }}
            disabled={!item.dataId && !hasChildren}
          >
            <span className="flex-1 truncate">{item.name}</span>
            {item.count !== undefined && <span className="ml-3 text-xs text-gray-500">({item.count})</span>}
            {hasChildren && (
              <svg
                className={`w-4 h-4 text-gray-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            )}
          </button>
          {hasChildren && isExpanded && <div className="pl-4">{renderTreeItems(item.children!)}</div>}
        </div>
      )
    })

  const hasActiveFilters =
    filters.categories.length > 0 ||
    filters.brands.length > 0 ||
    filters.subcategories.length > 0 ||
    filters.priceMin !== undefined ||
    filters.priceMax !== undefined ||
    filters.inStock ||
    (filters.shoeTypes && filters.shoeTypes.length > 0) ||
    (filters.clothingItems && filters.clothingItems.length > 0) ||
    (filters.jewelryMaterials && filters.jewelryMaterials.length > 0) ||
    (filters.jewelryGender && filters.jewelryGender.length > 0) ||
    (filters.headwearTypes && filters.headwearTypes.length > 0)

  const toggleCustomFilter = (field: 'shoeTypes' | 'clothingItems' | 'jewelryMaterials' | 'jewelryGender' | 'headwearTypes', value: string) => {
    setFilters((prev) => {
      const current = prev[field] || []
      const exists = current.includes(value)
      const nextArr = exists ? current.filter((v) => v !== value) : [...current, value]
      return { ...prev, [field]: nextArr }
    })
  }

  const shoeTypeOptions = [
    { value: 'sneakers', label: 'Кроссовки' },
    { value: 'boots', label: 'Ботинки/Ботильоны' },
    { value: 'sandals', label: 'Сандалии/Шлёпанцы' },
  ]

  const clothingItemOptions = [
    { value: 'jeans', label: 'Джинсы' },
    { value: 'tshirts', label: 'Футболки' },
    { value: 'hoodies', label: 'Худи' },
    { value: 'sweaters', label: 'Джемперы/Свитеры' },
    { value: 'shirts', label: 'Рубашки' },
    { value: 'blouses', label: 'Блузки' },
    { value: 'jackets', label: 'Куртки' },
    { value: 'coats', label: 'Пальто' },
    { value: 'trousers', label: 'Брюки' },
    { value: 'shorts', label: 'Шорты' },
    { value: 'socks', label: 'Носки' },
    { value: 'dresses', label: 'Платья' },
    { value: 'skirts', label: 'Юбки' },
  ]

  const jewelryMaterialOptions = [
    { value: 'gold', label: 'Золото' },
    { value: 'silver', label: 'Серебро' },
    { value: 'bijouterie', label: 'Бижутерия' },
  ]

  const jewelryGenderOptions = [
    { value: 'women', label: 'Женские' },
    { value: 'men', label: 'Мужские' },
    { value: 'kids', label: 'Детские' },
  ]

  const headwearTypeOptions = [
    { value: 'caps', label: 'Кепки' },
    { value: 'hats', label: 'Шапки' },
    { value: 'panama', label: 'Панамки' },
  ]

  return (
    <>
      {isOpen && <div className="fixed inset-0 bg-black bg-opacity-50 z-40 lg:hidden" onClick={onToggle} />}
      <aside
        className={`
          fixed lg:sticky top-16 lg:top-20 left-0 z-30
          h-full lg:h-auto lg:max-h-[calc(100vh-2rem)]
          w-80 bg-white/95 backdrop-blur text-gray-900 border-r lg:border-r-0 lg:border border-gray-200 rounded-2xl
          shadow-[0_20px_60px_-20px_rgba(255,255,255,0.65),0_20px_50px_-18px_rgba(109,40,217,0.45)] lg:shadow-sm
          transform transition-transform duration-300 ease-in-out
          overflow-y-auto
          ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
        `}
      >
        <div className="p-6 space-y-6">
          <div className="flex items-center justify-between border-b border-[var(--border)] pb-4">
            <h2 className="text-xl font-bold text-main dark:text-gray-900">Фильтры</h2>
            <div className="flex items-center gap-2">
              {hasActiveFilters && (
                <button onClick={clearFilters} className="text-sm text-violet-600 hover:text-violet-800 font-medium">
                  Сбросить
                </button>
              )}
              <button onClick={onToggle} className="lg:hidden text-main/70 hover:text-main dark:text-gray-500 dark:hover:text-gray-700">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {categoryGroups.length > 0 && (
            <div className="space-y-5 border-b pb-4">
              {categoryGroups.map((group) => {
                // Если первый элемент уже содержит название группы, не показываем заголовок отдельно
                const firstItem = group.items[0]
                const shouldHideTitle = firstItem && firstItem.name === group.title
                return (
                  <div key={group.title}>
                    {!shouldHideTitle && (
                      <h3 className="text-base font-semibold text-main mb-3 dark:text-gray-900">{group.title}</h3>
                    )}
                    <div className="space-y-1">{renderTreeItems(group.items)}</div>
                  </div>
                )
              })}
            </div>
          )}

          {/* Спец-фильтры: обувь */}
          {categoryType === 'shoes' && (
            <div className="border-b pb-4">
              <button
                onClick={() => setExpandedSections((prev) => ({ ...prev, filters: !prev.filters }))}
                className="flex items-center justify-between w-full mb-3"
              >
                <h3 className="text-base font-semibold text-main dark:text-gray-900">Тип обуви</h3>
                <svg
                  className={`w-5 h-5 text-main/60 dark:text-gray-500 transition-transform ${expandedSections.filters ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {expandedSections.filters && (
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {shoeTypeOptions.map((opt) => (
                    <label key={opt.value} className="flex items-center space-x-2 cursor-pointer group">
                      <input
                        type="checkbox"
                        checked={filters.shoeTypes?.includes(opt.value) || false}
                        onChange={() => toggleCustomFilter('shoeTypes', opt.value)}
                        className="w-4 h-4 text-violet-600 border-gray-300 rounded focus:ring-violet-500"
                      />
                      <span className="text-sm text-main dark:text-gray-800 group-hover:text-violet-700 flex-1">{opt.label}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Спец-фильтры: одежда */}
          {categoryType === 'clothing' && (
            <div className="border-b pb-4">
              <button
                onClick={() => setExpandedSections((prev) => ({ ...prev, filters: !prev.filters }))}
                className="flex items-center justify-between w-full mb-3"
              >
                <h3 className="text-base font-semibold text-main dark:text-gray-900">Предметы одежды</h3>
                <svg
                  className={`w-5 h-5 text-main/60 dark:text-gray-500 transition-transform ${expandedSections.filters ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {expandedSections.filters && (
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {clothingItemOptions.map((opt) => (
                    <label key={opt.value} className="flex items-center space-x-2 cursor-pointer group">
                      <input
                        type="checkbox"
                        checked={filters.clothingItems?.includes(opt.value) || false}
                        onChange={() => toggleCustomFilter('clothingItems', opt.value)}
                        className="w-4 h-4 text-violet-600 border-gray-300 rounded focus:ring-violet-500"
                      />
                      <span className="text-sm text-main dark:text-gray-800 group-hover:text-violet-700 flex-1">{opt.label}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Спец-фильтры: украшения */}
          {categoryType === 'jewelry' && (
            <div className="border-b pb-4 space-y-4">
              <div>
                <button
                  onClick={() => setExpandedSections((prev) => ({ ...prev, filters: !prev.filters }))}
                  className="flex items-center justify-between w-full mb-3"
                >
                  <h3 className="text-base font-semibold text-gray-900">Материал</h3>
                  <svg
                    className={`w-5 h-5 text-gray-500 transition-transform ${expandedSections.filters ? 'rotate-180' : ''}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
                {expandedSections.filters && (
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    {jewelryMaterialOptions.map((opt) => (
                      <label key={opt.value} className="flex items-center space-x-2 cursor-pointer group">
                        <input
                          type="checkbox"
                          checked={filters.jewelryMaterials?.includes(opt.value) || false}
                          onChange={() => toggleCustomFilter('jewelryMaterials', opt.value)}
                          className="w-4 h-4 text-violet-600 border-gray-300 rounded focus:ring-violet-500"
                        />
                        <span className="text-sm text-gray-700 group-hover:text-violet-700 flex-1">{opt.label}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <button
                  onClick={() => setExpandedSections((prev) => ({ ...prev, brands: !prev.brands }))}
                  className="flex items-center justify-between w-full mb-3"
                >
                  <h3 className="text-base font-semibold text-gray-900">Для кого</h3>
                  <svg
                    className={`w-5 h-5 text-gray-500 transition-transform ${expandedSections.brands ? 'rotate-180' : ''}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
                {expandedSections.brands && (
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    {jewelryGenderOptions.map((opt) => (
                      <label key={opt.value} className="flex items-center space-x-2 cursor-pointer group">
                        <input
                          type="checkbox"
                          checked={filters.jewelryGender?.includes(opt.value) || false}
                          onChange={() => toggleCustomFilter('jewelryGender', opt.value)}
                          className="w-4 h-4 text-violet-600 border-gray-300 rounded focus:ring-violet-500"
                        />
                        <span className="text-sm text-gray-700 group-hover:text-violet-700 flex-1">{opt.label}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Спец-фильтры: головные уборы */}
          {categoryType === 'headwear' && (
            <div className="border-b pb-4">
              <button
                onClick={() => setExpandedSections((prev) => ({ ...prev, filters: !prev.filters }))}
                className="flex items-center justify-between w-full mb-3"
              >
                <h3 className="text-base font-semibold text-gray-900">Тип головного убора</h3>
                <svg
                  className={`w-5 h-5 text-gray-500 transition-transform ${expandedSections.filters ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {expandedSections.filters && (
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {headwearTypeOptions.map((opt) => (
                    <label key={opt.value} className="flex items-center space-x-2 cursor-pointer group">
                      <input
                        type="checkbox"
                        checked={filters.headwearTypes?.includes(opt.value) || false}
                        onChange={() => toggleCustomFilter('headwearTypes', opt.value)}
                        className="w-4 h-4 text-violet-600 border-gray-300 rounded focus:ring-violet-500"
                      />
                      <span className="text-sm text-gray-700 group-hover:text-violet-700 flex-1">{opt.label}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}

          {categories.length > 0 && categoryGroups.length === 0 && (
            <div className="border-b pb-4">
              <button
                onClick={() => setExpandedSections((prev) => ({ ...prev, categories: !prev.categories }))}
                className="flex items-center justify-between w-full mb-3"
              >
                <h3 className="text-base font-semibold text-gray-900">Категории</h3>
                <svg
                  className={`w-5 h-5 text-gray-500 transition-transform ${expandedSections.categories ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {expandedSections.categories && (
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {categories.map((category) => (
                    <label key={category.id} className="flex items-center space-x-2 cursor-pointer group">
                      <input
                        type="checkbox"
                        checked={filters.categories.includes(category.id)}
                        onChange={() => toggleCategoryFilter(category.id, ensureSlug(category.slug))}
                        className="w-4 h-4 text-violet-600 border-gray-300 rounded focus:ring-violet-500"
                      />
                      <span className="text-sm text-gray-700 group-hover:text-violet-700 flex-1">{category.name}</span>
                      {category.product_count !== undefined && (
                        <span className="text-xs text-gray-500">({category.product_count})</span>
                      )}
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}

          {showSubcategories && subcategories.length > 0 && (
            <div className="border-b pb-4">
              <button
                onClick={() => setExpandedSections((prev) => ({ ...prev, subcategories: !prev.subcategories }))}
                className="flex items-center justify-between w-full mb-3"
              >
                <h3 className="text-base font-semibold text-gray-900">Подкатегории</h3>
                <svg
                  className={`w-5 h-5 text-gray-500 transition-transform ${expandedSections.subcategories ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {expandedSections.subcategories && (
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {subcategories.map((subcategory) => (
                    <label key={subcategory.id} className="flex items-center space-x-2 cursor-pointer group">
                      <input
                        type="checkbox"
                        checked={filters.subcategories.includes(subcategory.id)}
                        onChange={() => toggleSubcategoryFilter(subcategory.id, ensureSlug(subcategory.slug))}
                        className="w-4 h-4 text-violet-600 border-gray-300 rounded focus:ring-violet-500"
                      />
                      <span className="text-sm text-gray-700 group-hover:text-violet-700 flex-1">{subcategory.name}</span>
                      {subcategory.product_count !== undefined && (
                        <span className="text-xs text-gray-500">({subcategory.product_count})</span>
                      )}
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}

          {brandGroups.length > 0 && (
            <div className="border-b pb-4">
              {brandGroups.map((group) => (
                <div key={group.title}>
                  <h3 className="text-base font-semibold text-gray-900 mb-3">{group.title}</h3>
                  <div className="space-y-1">{renderTreeItems(group.items)}</div>
                </div>
              ))}
            </div>
          )}

          {brands.length > 0 && brandGroups.length === 0 && (
            <div className="border-b pb-4">
              <button
                onClick={() => setExpandedSections((prev) => ({ ...prev, brands: !prev.brands }))}
                className="flex items-center justify-between w-full mb-3"
              >
                <h3 className="text-base font-semibold text-gray-900">Бренды</h3>
                <svg
                  className={`w-5 h-5 text-gray-500 transition-transform ${expandedSections.brands ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {expandedSections.brands && (
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {brands.map((brand) => (
                    <label key={brand.id} className="flex items-center space-x-2 cursor-pointer group">
                      <input
                        type="checkbox"
                        checked={filters.brands.includes(brand.id)}
                        onChange={() => toggleBrandFilter(brand.id, ensureSlug(brand.slug))}
                        className="w-4 h-4 text-violet-600 border-gray-300 rounded focus:ring-violet-500"
                      />
                      <div className="flex items-center space-x-2 flex-1">
                        {/* Логотипы брендов временно скрыты по просьбе пользователя */}
                        <span className="text-sm text-gray-700 group-hover:text-violet-700">{brand.name}</span>
                      </div>
                      {brand.product_count !== undefined && (
                        <span className="text-xs text-gray-500">({brand.product_count})</span>
                      )}
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="border-b pb-4">
            <button
              onClick={() => setExpandedSections((prev) => ({ ...prev, price: !prev.price }))}
              className="flex items-center justify-between w-full mb-3"
            >
              <h3 className="text-base font-semibold text-gray-900">Цена</h3>
              <svg
                className={`w-5 h-5 text-gray-500 transition-transform ${expandedSections.price ? 'rotate-180' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {expandedSections.price && (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    placeholder="От"
                    value={priceRange.min}
                    onChange={(e) => setPriceRange((prev) => ({ ...prev, min: e.target.value }))}
                    onBlur={handlePriceChange}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-violet-500 focus:border-violet-500"
                  />
                  <span className="text-gray-500">—</span>
                  <input
                    type="number"
                    placeholder="До"
                    value={priceRange.max}
                    onChange={(e) => setPriceRange((prev) => ({ ...prev, max: e.target.value }))}
                    onBlur={handlePriceChange}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-violet-500 focus:border-violet-500"
                  />
                </div>
              </div>
            )}
          </div>

          <div className="border-b pb-4">
            <h3 className="text-base font-semibold text-gray-900 mb-3">Сортировка</h3>
            <select
              value={filters.sortBy}
              onChange={(e) => updateFilters((prev) => ({ ...prev, sortBy: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-violet-500 focus:border-violet-500"
            >
              <option value="name_asc">По названию (А-Я)</option>
              <option value="name_desc">По названию (Я-А)</option>
              <option value="price_asc">По цене (возрастание)</option>
              <option value="price_desc">По цене (убывание)</option>
              <option value="newest">Сначала новые</option>
              <option value="popular">Популярные</option>
            </select>
          </div>

          <div>
            <button
              onClick={() => setExpandedSections((prev) => ({ ...prev, filters: !prev.filters }))}
              className="flex items-center justify-between w-full mb-3"
            >
              <h3 className="text-base font-semibold text-gray-900">Дополнительно</h3>
              <svg
                className={`w-5 h-5 text-gray-500 transition-transform ${expandedSections.filters ? 'rotate-180' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {expandedSections.filters && (
              <div className="space-y-3">
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={filters.inStock}
                    onChange={(e) =>
                      updateFilters((prev) => ({
                        ...prev,
                        inStock: e.target.checked
                      }))
                    }
                    className="w-4 h-4 text-violet-600 border-gray-300 rounded focus:ring-violet-500"
                  />
                  <span className="text-sm text-gray-700">{t('sidebar_in_stock')}</span>
                </label>
              </div>
            )}
          </div>
        </div>
      </aside>
    </>
  )
}
