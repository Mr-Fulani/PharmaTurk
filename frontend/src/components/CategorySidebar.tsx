import { useState, useEffect, useMemo } from 'react'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import { getLocalizedCategoryName, getLocalizedBrandName, CategoryTranslation, BrandTranslation } from '../lib/i18n'

export interface SidebarTreeItem {
  id: string
  name: string
  nameKey?: string
  slug?: string
  dataId?: number
  count?: number
  type?: 'category' | 'brand' | 'subcategory'
  children?: SidebarTreeItem[]
}

export interface SidebarTreeSection {
  title: string
  titleKey?: string
  items: SidebarTreeItem[]
}

export interface FilterState {
  categories: number[]
  categorySlugs: string[]
  brands: number[]
  brandSlugs: string[]
  subcategories: number[]
  subcategorySlugs: string[]
  authorIds?: number[]
  genreIds?: number[]
  publishers?: string[]
  languages?: string[]
  priceMin?: number
  priceMax?: number
  inStock: boolean
  isNew: boolean
  sortBy: string
  colors?: string[]
  sizes?: string[]
  shoeTypes?: string[]
  clothingItems?: string[]
  jewelryMaterials?: string[]
  jewelryGender?: string[]
  headwearTypes?: string[]
  furnitureTypes?: string[]
}

interface Category {
  id: number
  name: string
  slug: string
  children_count?: number
  product_count?: number
  translations?: CategoryTranslation[]
}

interface Brand {
  id: number
  name: string
  slug: string
  logo?: string
  product_count?: number
  translations?: BrandTranslation[]
}

interface BookAuthorOption {
  id: number
  name: string
}

interface CategorySidebarProps {
  categories?: Category[]
  brands?: Brand[]
  subcategories?: Category[]
  bookAuthors?: BookAuthorOption[]
  bookGenres?: Category[]
  bookPublishers?: string[]
  bookLanguages?: string[]
  categoryGroups?: SidebarTreeSection[]
  brandGroups?: SidebarTreeSection[]
  onFilterChange?: (filters: FilterState) => void
  isOpen?: boolean
  onToggle?: () => void
  initialFilters?: FilterState
  showSubcategories?: boolean
  showCategories?: boolean
  categoryType?: string
}

const toggleArrayValue = <T,>(arr: T[], value: T): T[] =>
  arr.includes(value) ? arr.filter((item) => item !== value) : [...arr, value]

const ensureSlug = (value?: string) => (value ? value.trim().toLowerCase().replace(/\s+/g, '-') : '')

const normalizeKeyword = (value?: string | null) =>
  (value || '')
    .toString()
    .trim()
    .toLowerCase()
    .replace(/_/g, '-')

const parseNumber = (value: string | number | null | undefined) => {
  if (value === null || typeof value === 'undefined') return null
  const normalized = String(value).replace(',', '.').replace(/[^0-9.]/g, '')
  if (!normalized) return null
  const num = Number(normalized)
  return Number.isFinite(num) ? num : null
}

const detectJewelryTypeKey = (value?: string | null) => {
  const s = normalizeKeyword(value)
  if (!s) return null
  if (s.includes('ring') || s.includes('кольц') || s.includes('obruch') || s.includes('wedding')) return 'ring'
  if (s.includes('bracelet') || s.includes('браслет')) return 'bracelet'
  if (s.includes('necklace') || s.includes('chain') || s.includes('цеп') || s.includes('цепоч')) return 'necklace'
  if (s.includes('earring') || s.includes('серьг')) return 'earrings'
  if (s.includes('pendant') || s.includes('подвес')) return 'pendant'
  return null
}

export default function CategorySidebar({
  categories = [],
  brands = [],
  subcategories = [],
  bookAuthors = [],
  bookGenres = [],
  bookPublishers = [],
  bookLanguages = [],
  categoryGroups = [],
  brandGroups = [],
  onFilterChange,
  isOpen = true,
  onToggle,
  initialFilters,
  showSubcategories = false,
  showCategories = true,
  categoryType
}: CategorySidebarProps) {
  const { t } = useTranslation('common')
  const router = useRouter()
  const defaultFilters: FilterState = {
    categories: [],
    categorySlugs: [],
    brands: [],
    brandSlugs: [],
    subcategories: [],
    subcategorySlugs: [],
    authorIds: [],
    genreIds: [],
    publishers: [],
    languages: [],
    priceMin: undefined,
    priceMax: undefined,
    inStock: false,
    isNew: false,
    sortBy: 'name_asc',
    shoeTypes: [],
    clothingItems: [],
    jewelryMaterials: [],
    jewelryGender: [],
    headwearTypes: [],
    furnitureTypes: [],
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
    initialFilters?.authorIds?.join(','),
    initialFilters?.genreIds?.join(','),
    initialFilters?.publishers?.join(','),
    initialFilters?.languages?.join(','),
    initialFilters?.furnitureTypes?.join(','),
    initialFilters?.inStock,
    initialFilters?.isNew,
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
    filters: true,
    bookFilters: true
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
    filters.authorIds?.join(','),
    filters.genreIds?.join(','),
    filters.publishers?.join(','),
    filters.languages?.join(','),
    filters.priceMin,
    filters.priceMax,
    filters.inStock,
    filters.isNew,
    filters.sortBy,
    filters.shoeTypes?.join(','),
    filters.clothingItems?.join(','),
    filters.jewelryMaterials?.join(','),
    filters.jewelryGender?.join(','),
    filters.headwearTypes?.join(','),
    filters.furnitureTypes?.join(',')
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

  const toggleAuthorFilter = (authorId: number) => {
    updateFilters((prev) => ({
      ...prev,
      authorIds: toggleArrayValue(prev.authorIds || [], authorId)
    }))
  }

  const toggleGenreFilter = (genreId: number) => {
    updateFilters((prev) => ({
      ...prev,
      genreIds: toggleArrayValue(prev.genreIds || [], genreId)
    }))
  }

  const togglePublisherFilter = (publisher: string) => {
    updateFilters((prev) => ({
      ...prev,
      publishers: toggleArrayValue(prev.publishers || [], publisher)
    }))
  }

  const toggleLanguageFilter = (language: string) => {
    updateFilters((prev) => ({
      ...prev,
      languages: toggleArrayValue(prev.languages || [], language)
    }))
  }

  const getJewelrySubcategoryKey = (subcategory: Category) => {
    const slug = subcategory.slug || ''
    const name = subcategory.name || ''
    const slugType = detectJewelryTypeKey(slug)
    const nameType = detectJewelryTypeKey(name)
    if (nameType && (!slugType || nameType !== slugType)) {
      return name
    }
    return slug || name
  }

  const getSubcategoryLabel = (subcategory: Category) => {
    const localized = getLocalizedCategoryName(subcategory.slug, subcategory.name, t, subcategory.translations, router.locale)
    if (categoryType === 'shoes') {
      return localized.replace(/\s*\([^)]*\)\s*$/, '')
    }
    if (categoryType !== 'jewelry') return localized
    const locale = router.locale || 'ru'
    const name = subcategory.name || ''
    const slugType = detectJewelryTypeKey(subcategory.slug || '')
    const nameType = detectJewelryTypeKey(name)
    if (locale.startsWith('ru') && name && nameType && slugType && nameType !== slugType) {
      return name
    }
    return localized
  }

  const uniqueSubcategories = useMemo(() => {
    const normalizeLabel = (label: string) => {
      let normalized = label.toLowerCase().replace(/\s+/g, ' ').trim()
      if (categoryType === 'furniture') {
        normalized = normalized
          .replace(/^мебель для\s+/, '')
          .replace(/^мебель\s+/, '')
          .replace(/^furniture for\s+/, '')
          .replace(/^furniture\s+/, '')
          .trim()
      }
      return normalized
    }
    const seen = new Set<string>()
    return subcategories.filter((subcategory) => {
      const rawLabel = getSubcategoryLabel(subcategory)
      const rawNormalized = rawLabel.toLowerCase().replace(/\s+/g, ' ').trim()
      if (categoryType === 'furniture' && rawNormalized.startsWith('мебель для гостин')) {
        return false
      }
      const key = normalizeLabel(rawLabel)
      if (!key) return true
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
  }, [subcategories, categoryType, t, router.locale])

  const handlePriceChange = () => {
    const minValue = parseNumber(priceRange.min)
    const maxValue = parseNumber(priceRange.max)
    updateFilters((prev) => ({
      ...prev,
      priceMin: minValue ?? undefined,
      priceMax: maxValue ?? undefined
    }))
  }

  const handlePriceInputChange = (field: 'min' | 'max', value: string) => {
    setPriceRange((prev) => {
      const next = { ...prev, [field]: value }
      const minValue = parseNumber(next.min)
      const maxValue = parseNumber(next.max)
      updateFilters((prevFilters) => ({
        ...prevFilters,
        priceMin: minValue ?? undefined,
        priceMax: maxValue ?? undefined
      }))
      return next
    })
  }

  const clearFilters = () => {
    setFilters({
      categories: [],
      categorySlugs: [],
      brands: [],
      brandSlugs: [],
      subcategories: [],
      subcategorySlugs: [],
      authorIds: [],
      genreIds: [],
      publishers: [],
      languages: [],
      priceMin: undefined,
      priceMax: undefined,
      inStock: false,
      isNew: false,
      sortBy: 'name_asc',
      shoeTypes: [],
      clothingItems: [],
      jewelryMaterials: [],
      jewelryGender: [],
      headwearTypes: [],
      furnitureTypes: []
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
            className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm font-medium ${item.dataId ? 'text-gray-700 hover:text-violet-700 cursor-pointer' : 'text-gray-400 cursor-not-allowed'
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
            <span className="flex-1 truncate">
              {item.nameKey
                ? t(item.nameKey)
                : item.slug && item.type === 'category'
                  ? getLocalizedCategoryName(item.slug, item.name, t, undefined, router.locale)
                  : item.type === 'brand' && item.slug
                    ? getLocalizedBrandName(item.slug, item.name, t, undefined, router.locale)
                    : item.name
              }
            </span>
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
    filters.isNew ||
    (filters.shoeTypes && filters.shoeTypes.length > 0) ||
    (filters.clothingItems && filters.clothingItems.length > 0) ||
    (filters.jewelryMaterials && filters.jewelryMaterials.length > 0) ||
    (filters.jewelryGender && filters.jewelryGender.length > 0) ||
    (filters.headwearTypes && filters.headwearTypes.length > 0) ||
    (filters.furnitureTypes && filters.furnitureTypes.length > 0) ||
    (filters.authorIds && filters.authorIds.length > 0) ||
    (filters.genreIds && filters.genreIds.length > 0) ||
    (filters.publishers && filters.publishers.length > 0) ||
    (filters.languages && filters.languages.length > 0)

  const toggleCustomFilter = (field: 'shoeTypes' | 'clothingItems' | 'jewelryMaterials' | 'jewelryGender' | 'headwearTypes' | 'furnitureTypes', value: string) => {
    setFilters((prev) => {
      const current = prev[field] || []
      const exists = current.includes(value)
      const nextArr = exists ? current.filter((v) => v !== value) : [...current, value]
      return { ...prev, [field]: nextArr }
    })
  }

  const shoeTypeOptions = [
    { value: 'sneakers', label: t('filter_sneakers', 'Кроссовки') },
    { value: 'boots', label: t('filter_boots', 'Ботинки/Ботильоны') },
    { value: 'sandals', label: t('filter_sandals', 'Сандалии/Шлёпанцы') },
    { value: 'shoes', label: t('filter_shoes', 'Туфли') },
    { value: 'home-shoes', label: t('filter_home_shoes', 'Домашняя обувь/Тапки') },
    { value: 'loafers', label: t('filter_loafers', 'Лоферы/Мокасины') },
  ]

  const clothingItemOptions = [
    { value: 'jeans', label: t('filter_jeans', 'Джинсы') },
    { value: 'tshirts', label: t('filter_tshirts', 'Футболки') },
    { value: 'hoodies', label: t('filter_hoodies', 'Худи') },
    { value: 'sweaters', label: t('filter_sweaters', 'Джемперы/Свитеры') },
    { value: 'shirts', label: t('filter_shirts', 'Рубашки') },
    { value: 'blouses', label: t('filter_blouses', 'Блузки') },
    { value: 'jackets', label: t('filter_jackets', 'Куртки') },
    { value: 'coats', label: t('filter_coats', 'Пальто') },
    { value: 'trousers', label: t('filter_trousers', 'Брюки') },
    { value: 'shorts', label: t('filter_shorts', 'Шорты') },
    { value: 'socks', label: t('filter_socks', 'Носки') },
    { value: 'dresses', label: t('filter_dresses', 'Платья') },
    { value: 'skirts', label: t('filter_skirts', 'Юбки') },
  ]

  const jewelryMaterialOptions = [
    { value: 'gold', label: t('filter_gold', 'Золото') },
    { value: 'silver', label: t('filter_silver', 'Серебро') },
    { value: 'bijouterie', label: t('filter_bijouterie', 'Бижутерия') },
  ]

  const jewelryGenderOptions = [
    { value: 'women', label: t('filter_women', 'Женские') },
    { value: 'men', label: t('filter_men', 'Мужские') },
    { value: 'unisex', label: t('filter_unisex', 'Унисекс') },
    { value: 'kids', label: t('filter_kids', 'Детские') },
  ]

  const headwearTypeOptions = [
    { value: 'caps', label: t('filter_caps', 'Кепки') },
    { value: 'hats', label: t('filter_hats', 'Шапки') },
    { value: 'panama', label: t('filter_panama', 'Панамки') },
  ]

  const furnitureTypeOptions = [
    { value: 'chairs', label: t('filter_chairs', 'Стулья') },
    { value: 'tables', label: t('filter_tables', 'Столы') },
    { value: 'wardrobes', label: t('filter_wardrobes', 'Шкафы') },
    { value: 'sofas', label: t('filter_sofas', 'Диваны') },
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
            <h2 className="text-xl font-bold text-main dark:text-gray-900">{t('sidebar_filters', 'Фильтры')}</h2>
            <div className="flex items-center gap-2">
              {hasActiveFilters && (
                <button onClick={clearFilters} className="text-sm text-[var(--accent)] hover:text-[var(--accent-strong)] font-medium">
                  {t('sidebar_reset', 'Сбросить')}
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
                const sectionTitle = group.titleKey ? t(group.titleKey) : group.title
                return (
                  <div key={group.title}>
                    {!shouldHideTitle && (
                      <h3 className="text-base font-semibold text-main mb-3 dark:text-gray-900">{sectionTitle}</h3>
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
                <h3 className="text-base font-semibold text-main dark:text-gray-900">{t('sidebar_shoe_types', 'Тип обуви')}</h3>
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
                <h3 className="text-base font-semibold text-main dark:text-gray-900">{t('sidebar_clothing_items', 'Предметы одежды')}</h3>
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
                  <h3 className="text-base font-semibold text-gray-900">{t('sidebar_jewelry_material', 'Материал')}</h3>
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
                  <h3 className="text-base font-semibold text-gray-900">{t('sidebar_jewelry_gender', 'Для кого')}</h3>
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
                <h3 className="text-base font-semibold text-gray-900">{t('sidebar_headwear_types', 'Тип головного убора')}</h3>
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

          {categoryType === 'furniture' && (
            <div className="border-b pb-4">
              <button
                onClick={() => setExpandedSections((prev) => ({ ...prev, filters: !prev.filters }))}
                className="flex items-center justify-between w-full mb-3"
              >
                <h3 className="text-base font-semibold text-gray-900">{t('sidebar_furniture_type', 'Тип мебели')}</h3>
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
                  {furnitureTypeOptions.map((opt) => (
                    <label key={opt.value} className="flex items-center space-x-2 cursor-pointer group">
                      <input
                        type="checkbox"
                        checked={filters.furnitureTypes?.includes(opt.value) || false}
                        onChange={() => toggleCustomFilter('furnitureTypes', opt.value)}
                        className="w-4 h-4 text-violet-600 border-gray-300 rounded focus:ring-violet-500"
                      />
                      <span className="text-sm text-gray-700 group-hover:text-violet-700 flex-1">{opt.label}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}

          {showCategories && categories.length > 0 && categoryGroups.length === 0 && subcategories.length === 0 && (
            <div className="border-b pb-4">
              <button
                onClick={() => setExpandedSections((prev) => ({ ...prev, categories: !prev.categories }))}
                className="flex items-center justify-between w-full mb-3"
              >
                <h3 className="text-base font-semibold text-gray-900">{t('sidebar_categories', 'Категории')}</h3>
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
                      <span className="text-sm text-gray-700 group-hover:text-violet-700 flex-1">
                        {getLocalizedCategoryName(category.slug, category.name, t, category.translations, router.locale)}
                      </span>
                      {category.product_count !== undefined && (
                        <span className="text-xs text-gray-500">({category.product_count})</span>
                      )}
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}

          {showSubcategories && uniqueSubcategories.length > 0 && categoryGroups.length === 0 && (
            <div className="border-b pb-4">
              <button
                onClick={() => setExpandedSections((prev) => ({ ...prev, subcategories: !prev.subcategories }))}
                className="flex items-center justify-between w-full mb-3"
              >
                <h3 className="text-base font-semibold text-gray-900">{t('sidebar_subcategories', 'Подкатегории')}</h3>
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
                  {uniqueSubcategories.map((subcategory) => (
                    <label key={subcategory.id} className="flex items-center space-x-2 cursor-pointer group">
                      <input
                        type="checkbox"
                        checked={filters.subcategories.includes(subcategory.id)}
                        onChange={() =>
                          toggleSubcategoryFilter(
                            subcategory.id,
                            categoryType === 'jewelry' ? getJewelrySubcategoryKey(subcategory) : subcategory.slug
                          )
                        }
                        className="w-4 h-4 text-violet-600 border-gray-300 rounded focus:ring-violet-500"
                      />
                      <span className="text-sm text-gray-700 group-hover:text-violet-700 flex-1">
                        {getSubcategoryLabel(subcategory)}
                      </span>
                      {subcategory.product_count !== undefined && (
                        <span className="text-xs text-gray-500">({subcategory.product_count})</span>
                      )}
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}

          {categoryType === 'books' && (bookAuthors.length > 0 || bookGenres.length > 0 || bookPublishers.length > 0 || bookLanguages.length > 0) && (
            <div className="border-b pb-4 space-y-4">
              {bookAuthors.length > 0 && (
                <div>
                  <button
                    onClick={() => setExpandedSections((prev) => ({ ...prev, bookFilters: !prev.bookFilters }))}
                    className="flex items-center justify-between w-full mb-3"
                  >
                    <h3 className="text-base font-semibold text-gray-900">{t('sidebar_book_authors', 'Авторы')}</h3>
                    <svg
                      className={`w-5 h-5 text-gray-500 transition-transform ${expandedSections.bookFilters ? 'rotate-180' : ''}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                  {expandedSections.bookFilters && (
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                      {bookAuthors.map((author) => (
                        <label key={author.id} className="flex items-center space-x-2 cursor-pointer group">
                          <input
                            type="checkbox"
                            checked={filters.authorIds?.includes(author.id) || false}
                            onChange={() => toggleAuthorFilter(author.id)}
                            className="w-4 h-4 text-violet-600 border-gray-300 rounded focus:ring-violet-500"
                          />
                          <span className="text-sm text-gray-700 group-hover:text-violet-700 flex-1">{author.name}</span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {bookGenres.length > 0 && (
                <div>
                  <button
                    onClick={() => setExpandedSections((prev) => ({ ...prev, bookFilters: !prev.bookFilters }))}
                    className="flex items-center justify-between w-full mb-3"
                  >
                    <h3 className="text-base font-semibold text-gray-900">{t('sidebar_book_genres', 'Жанры')}</h3>
                    <svg
                      className={`w-5 h-5 text-gray-500 transition-transform ${expandedSections.bookFilters ? 'rotate-180' : ''}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                  {expandedSections.bookFilters && (
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                      {bookGenres.map((genre) => (
                        <label key={genre.id} className="flex items-center space-x-2 cursor-pointer group">
                          <input
                            type="checkbox"
                            checked={filters.genreIds?.includes(genre.id) || false}
                            onChange={() => toggleGenreFilter(genre.id)}
                            className="w-4 h-4 text-violet-600 border-gray-300 rounded focus:ring-violet-500"
                          />
                          <span className="text-sm text-gray-700 group-hover:text-violet-700 flex-1">
                            {getLocalizedCategoryName(genre.slug, genre.name, t, genre.translations, router.locale)}
                          </span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {bookPublishers.length > 0 && (
                <div>
                  <button
                    onClick={() => setExpandedSections((prev) => ({ ...prev, bookFilters: !prev.bookFilters }))}
                    className="flex items-center justify-between w-full mb-3"
                  >
                    <h3 className="text-base font-semibold text-gray-900">{t('sidebar_book_publishers', 'Издательства')}</h3>
                    <svg
                      className={`w-5 h-5 text-gray-500 transition-transform ${expandedSections.bookFilters ? 'rotate-180' : ''}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                  {expandedSections.bookFilters && (
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                      {bookPublishers.map((publisher) => (
                        <label key={publisher} className="flex items-center space-x-2 cursor-pointer group">
                          <input
                            type="checkbox"
                            checked={filters.publishers?.includes(publisher) || false}
                            onChange={() => togglePublisherFilter(publisher)}
                            className="w-4 h-4 text-violet-600 border-gray-300 rounded focus:ring-violet-500"
                          />
                          <span className="text-sm text-gray-700 group-hover:text-violet-700 flex-1">{publisher}</span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {bookLanguages.length > 0 && (
                <div>
                  <button
                    onClick={() => setExpandedSections((prev) => ({ ...prev, bookFilters: !prev.bookFilters }))}
                    className="flex items-center justify-between w-full mb-3"
                  >
                    <h3 className="text-base font-semibold text-gray-900">{t('sidebar_book_languages', 'Язык')}</h3>
                    <svg
                      className={`w-5 h-5 text-gray-500 transition-transform ${expandedSections.bookFilters ? 'rotate-180' : ''}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                  {expandedSections.bookFilters && (
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                      {bookLanguages.map((language) => (
                        <label key={language} className="flex items-center space-x-2 cursor-pointer group">
                          <input
                            type="checkbox"
                            checked={filters.languages?.includes(language) || false}
                            onChange={() => toggleLanguageFilter(language)}
                            className="w-4 h-4 text-violet-600 border-gray-300 rounded focus:ring-violet-500"
                          />
                          <span className="text-sm text-gray-700 group-hover:text-violet-700 flex-1">{language}</span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {brandGroups.length > 0 && categoryType !== 'books' && (
            <div className="border-b pb-4">
              {brandGroups.map((group) => (
                <div key={group.title}>
                  <h3 className="text-base font-semibold text-gray-900 mb-3">{group.title}</h3>
                  <div className="space-y-1">{renderTreeItems(group.items)}</div>
                </div>
              ))}
            </div>
          )}

          {brands.length > 0 && brandGroups.length === 0 && categoryType !== 'books' && (
            <div className="border-b pb-4">
              <button
                onClick={() => setExpandedSections((prev) => ({ ...prev, brands: !prev.brands }))}
                className="flex items-center justify-between w-full mb-3"
              >
                <h3 className="text-base font-semibold text-gray-900">{t('sidebar_brands', 'Бренды')}</h3>
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
                        <span className="text-sm text-gray-700 group-hover:text-violet-700">
                          {getLocalizedBrandName(brand.slug, brand.name, t, brand.translations, router.locale)}
                        </span>
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
              <h3 className="text-base font-semibold text-gray-900">{t('sidebar_price', 'Цена')}</h3>
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
                    placeholder={t('sidebar_price_from', 'От')}
                    value={priceRange.min}
                    onChange={(e) => handlePriceInputChange('min', e.target.value)}
                    onBlur={handlePriceChange}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-violet-500 focus:border-violet-500"
                  />
                  <span className="text-gray-500">—</span>
                  <input
                    type="number"
                    placeholder={t('sidebar_price_to', 'До')}
                    value={priceRange.max}
                    onChange={(e) => handlePriceInputChange('max', e.target.value)}
                    onBlur={handlePriceChange}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-violet-500 focus:border-violet-500"
                  />
                </div>
              </div>
            )}
          </div>

          <div className="border-b pb-4">
            <h3 className="text-base font-semibold text-gray-900 mb-3">{t('sidebar_sort', 'Сортировка')}</h3>
            <select
              value={filters.sortBy}
              onChange={(e) => updateFilters((prev) => ({ ...prev, sortBy: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-violet-500 focus:border-violet-500"
            >
              <option value="name_asc">{t('sidebar_sort_name_asc_short', 'По названию (А-Я)')}</option>
              <option value="name_desc">{t('sidebar_sort_name_desc_short', 'По названию (Я-А)')}</option>
              <option value="price_asc">{t('sidebar_sort_price_asc_short', 'По цене (возрастание)')}</option>
              <option value="price_desc">{t('sidebar_sort_price_desc_short', 'По цене (убывание)')}</option>
              <option value="newest">{t('sidebar_sort_newest', 'Сначала новые')}</option>
              <option value="popular">{t('sidebar_sort_popular', 'Популярные')}</option>
            </select>
          </div>

          <div>
            <button
              onClick={() => setExpandedSections((prev) => ({ ...prev, filters: !prev.filters }))}
              className="flex items-center justify-between w-full mb-3"
            >
              <h3 className="text-base font-semibold text-gray-900">{t('sidebar_additional', 'Дополнительно')}</h3>
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
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={filters.isNew}
                    onChange={(e) =>
                      updateFilters((prev) => ({
                        ...prev,
                        isNew: e.target.checked
                      }))
                    }
                    className="w-4 h-4 text-violet-600 border-gray-300 rounded focus:ring-violet-500"
                  />
                  <span className="text-sm text-gray-700">{t('sidebar_new', 'Новинки')}</span>
                </label>
              </div>
            )}
          </div>
        </div>
      </aside>
    </>
  )
}
