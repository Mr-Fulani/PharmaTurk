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
  translations?: CategoryTranslation[] | BrandTranslation[]
}

export interface SidebarTreeSection {
  title: string
  titleKey?: string
  items: SidebarTreeItem[]
}

export interface AvailableAttribute {
  key: string
  name: string
  values: string[]
}

export interface FilterState {
  categories: number[]
  categorySlugs: string[]
  brands: number[]
  brandSlugs: string[]
  subcategories: number[]
  subcategorySlugs: string[]
  genders?: string[]
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
  attributes?: Record<string, string[]>
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
  availableAttributes?: AvailableAttribute[]
  onFilterChange?: (filters: FilterState) => void
  isOpen?: boolean
  onToggle?: () => void
  initialFilters?: FilterState
  showSubcategories?: boolean
  showCategories?: boolean
  showGenderFilter?: boolean
  categoryType?: string
}

const GENDER_OPTIONS = [
  { slug: 'women', key: 'filter_women', fallback: 'Женская' },
  { slug: 'men', key: 'filter_men', fallback: 'Мужская' },
  { slug: 'kids', key: 'filter_kids', fallback: 'Детская' },
  { slug: 'unisex', key: 'filter_unisex', fallback: 'Унисекс' },
]

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
  availableAttributes = [],
  onFilterChange,
  isOpen = true,
  onToggle,
  initialFilters,
  showSubcategories = false,
  showCategories = true,
  showGenderFilter = false,
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
    genders: [],
    authorIds: [],
    genreIds: [],
    publishers: [],
    languages: [],
    priceMin: undefined,
    priceMax: undefined,
    inStock: false,
    isNew: false,
    sortBy: 'name_asc',
    attributes: {},
  }
  const [filters, setFilters] = useState<FilterState>(initialFilters || defaultFilters)
  const [isMounted, setIsMounted] = useState(false)

  useEffect(() => {
    setIsMounted(true)
  }, [])

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
    initialFilters?.genders?.join(','),
    initialFilters?.authorIds?.join(','),
    initialFilters?.genreIds?.join(','),
    initialFilters?.publishers?.join(','),
    initialFilters?.languages?.join(','),
    JSON.stringify(initialFilters?.attributes || {}),
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
    gender: true,
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
    filters.genders?.join(','),
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
    JSON.stringify(filters.attributes || {})
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

  const toggleGenderFilter = (slug: string) => {
    updateFilters((prev) => ({
      ...prev,
      genders: toggleArrayValue(prev.genders || [], slug)
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
  }, [subcategories, categoryType, t, router.locale, isMounted])

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

  const toggleAttributeFilter = (key: string, value: string) => {
    updateFilters((prev) => {
      const current = prev.attributes?.[key] || []
      const exists = current.includes(value)
      const nextArr = exists ? current.filter((v) => v !== value) : [...current, value]
      const nextAttrs = { ...(prev.attributes || {}), [key]: nextArr }
      if (nextArr.length === 0) {
        const { [key]: _, ...rest } = nextAttrs
        return { ...prev, attributes: rest }
      }
      return { ...prev, attributes: nextAttrs }
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
      genders: [],
      authorIds: [],
      genreIds: [],
      publishers: [],
      languages: [],
      priceMin: undefined,
      priceMax: undefined,
      inStock: false,
      isNew: false,
      sortBy: 'name_asc',
      attributes: {}
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
      
      const isChecked = item.dataId 
        ? (item.type === 'brand' 
            ? filters.brands.includes(item.dataId) 
            : item.type === 'subcategory'
              ? filters.subcategories.includes(item.dataId)
              : filters.categories.includes(item.dataId))
        : false

      const labelContent = (
        <span className="flex-1 truncate">
          {item.nameKey
            ? t(item.nameKey, item.name)
            : item.slug && item.type === 'category'
              ? getLocalizedCategoryName(item.slug, item.name, t, item.translations as CategoryTranslation[], router.locale)
              : item.type === 'brand' && item.slug
                ? getLocalizedBrandName(item.slug, item.name, t, item.translations as BrandTranslation[], router.locale)
                : item.name
          }
        </span>
      )

      return (
        <div key={item.id} className="space-y-2">
          <div className="flex items-center group w-full">
            {item.dataId && (
              <input
                type="checkbox"
                checked={isChecked}
                onChange={(e) => {
                  e.stopPropagation()
                  if (item.type === 'brand') {
                    toggleBrandFilter(item.dataId!, item.slug || undefined)
                  } else if (item.type === 'subcategory') {
                    toggleSubcategoryFilter(item.dataId!, item.slug || undefined)
                  } else {
                    toggleCategoryFilter(item.dataId!, item.slug || undefined)
                  }
                }}
                className="w-4 h-4 text-[var(--accent)] border-[var(--border)] rounded focus:ring-[var(--accent)] mr-2 cursor-pointer transition-colors"
                id={`filter-item-${item.id}`}
              />
            )}
            <label
              htmlFor={`filter-item-${item.id}`}
              className={`flex-1 flex items-center justify-between rounded-md px-1 py-1 text-left text-sm font-medium transition-all ${
                item.dataId 
                  ? 'text-main hover:text-[var(--accent)] cursor-pointer' 
                  : 'text-gray-400 cursor-not-allowed'
              }`}
              onClick={(e) => {
                if (hasChildren) {
                  e.preventDefault()
                  toggleTreeItem(item.id)
                }
              }}
            >
              {labelContent}
              <div className="flex items-center space-x-2">
                {item.count !== undefined && <span className="text-xs text-main/50 font-normal">({item.count})</span>}
                {hasChildren && (
                  <svg
                    className={`w-4 h-4 text-main/40 group-hover:text-[var(--accent)]/60 transition-transform duration-300 ${isExpanded ? 'rotate-180' : ''}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                )}
              </div>
            </label>
          </div>
          {hasChildren && isExpanded && <div className="pl-6 border-l border-[var(--border)]/50 ml-2 mt-2 space-y-2">{renderTreeItems(item.children!)}</div>}
        </div>
      )
    })

  const hasActiveFilters =
    filters.categories.length > 0 ||
    filters.brands.length > 0 ||
    filters.subcategories.length > 0 ||
    (filters.genders && filters.genders.length > 0) ||
    filters.priceMin !== undefined ||
    filters.priceMax !== undefined ||
    filters.inStock ||
    filters.isNew ||
    (filters.attributes && Object.keys(filters.attributes).some((k) => (filters.attributes![k]?.length ?? 0) > 0)) ||
    (filters.authorIds && filters.authorIds.length > 0) ||
    (filters.genreIds && filters.genreIds.length > 0) ||
    (filters.publishers && filters.publishers.length > 0) ||
    (filters.languages && filters.languages.length > 0)

  return (
    <>
      {isOpen && <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[45] lg:hidden" onClick={onToggle} />}
      <aside
        suppressHydrationWarning
        className={`
          fixed lg:sticky top-0 lg:top-20 left-0 z-[50]
          h-[100dvh] lg:h-auto lg:max-h-[calc(100vh-2rem)]
          w-80 bg-[var(--bg)]/95 backdrop-blur-2xl text-main border-r lg:border-r-0 lg:border border-[var(--border)]
          shadow-[0_0_40px_rgba(0,0,0,0.2)] lg:shadow-md
          transform transition-all duration-300 ease-in-out
          overflow-y-auto custom-scrollbar
          ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
        `}
      >
        <div className="p-6 space-y-6">
          <div className="flex items-center justify-between border-b border-[var(--border)] pb-4">
            <h2 className="text-xl font-bold text-main">{t('sidebar_filters', 'Фильтры')}</h2>
            <div className="flex items-center gap-2">
              {hasActiveFilters && (
                <button 
                  onClick={clearFilters} 
                  className="text-xs px-2 py-1 rounded-full bg-[var(--accent-soft)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-white transition-all font-semibold"
                >
                  {t('sidebar_reset', 'Сбросить')}
                </button>
              )}
              <button onClick={onToggle} className="lg:hidden p-1 text-main/50 hover:text-main transition-colors">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {categoryGroups.length > 0 && categoryGroups.map((group) => {
            const firstItem = group.items[0]
            const shouldHideTitle = firstItem && firstItem.name === group.title
            const title = group.titleKey ? t(group.titleKey, group.title) : group.title
            const sectionTitle = title
            
            return (
              <div key={group.title} className="border-b border-[var(--border)] pb-2">
                {!shouldHideTitle ? (
                  <button
                    onClick={() => toggleTreeItem(`group-${group.title}`)}
                    className="flex items-center justify-between w-full mb-3 group"
                  >
                    <h3 className="text-base font-bold text-main group-hover:text-[var(--accent)] transition-colors uppercase tracking-tight">
                      {sectionTitle}
                    </h3>
                    <svg
                      className={`w-4 h-4 text-main/40 group-hover:text-[var(--accent)] transition-transform duration-300 ${expandedTreeItems[`group-${group.title}`] !== false ? 'rotate-180' : ''}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                ) : null}
                {(!shouldHideTitle && expandedTreeItems[`group-${group.title}`] !== false) || shouldHideTitle ? (
                  <div className="space-y-2 max-h-64 overflow-y-auto custom-scrollbar pr-1">{renderTreeItems(group.items)}</div>
                ) : null}
              </div>
            )
          })}

          {/* Универсальный фильтр по полу */}
          {showGenderFilter && (
            <div className="border-b border-[var(--border)] pb-4">
              <button
                onClick={() => setExpandedSections((prev) => ({ ...prev, gender: !prev.gender }))}
                className="flex items-center justify-between w-full mb-3 group"
              >
                <h3 className="text-base font-bold text-main group-hover:text-[var(--accent)] transition-colors uppercase tracking-tight">
                  {t('sidebar_gender', 'Пол')}
                </h3>
                <svg
                  className={`w-4 h-4 text-main/40 group-hover:text-[var(--accent)] transition-transform duration-300 ${expandedSections.gender ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {expandedSections.gender && (
                <div className="space-y-2">
                  {GENDER_OPTIONS.map((opt) => (
                    <label key={opt.slug} className="flex items-center space-x-3 cursor-pointer group">
                      <input
                        type="checkbox"
                        checked={(filters.genders || []).includes(opt.slug)}
                        onChange={() => toggleGenderFilter(opt.slug)}
                        className="w-4 h-4 text-[var(--accent)] border-[var(--border)] rounded focus:ring-[var(--accent)] transition-colors"
                        id={`gender-${opt.slug}`}
                      />
                      <span className="text-sm text-main group-hover:text-[var(--accent)] transition-colors flex-1">
                        {t(opt.key, opt.fallback)}
                      </span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Динамические атрибуты (фасетный поиск) */}
          {availableAttributes.length > 0 && (
            <div className="border-b pb-4 space-y-4">
              {availableAttributes.map((attr) => (
                <div key={attr.key}>
                  <h3 className="text-base font-semibold text-main mb-3">
                    {t(`attribute_${attr.key}`, attr.name)}
                  </h3>
                  <div className="space-y-2 max-h-64 overflow-y-auto custom-scrollbar">
                    {attr.values.map((val) => (
                      <label key={val} className="flex items-center space-x-3 cursor-pointer group">
                        <input
                          type="checkbox"
                          checked={filters.attributes?.[attr.key]?.includes(val) || false}
                          onChange={() => toggleAttributeFilter(attr.key, val)}
                          className="w-4 h-4 text-[var(--accent)] border-[var(--border)] rounded focus:ring-[var(--accent)] transition-colors"
                        />
                        <span className="text-sm text-main group-hover:text-[var(--accent)] transition-colors flex-1">
                          {t(`attr_val_${val.toLowerCase().replace(/\s+/g, '_')}`, val)}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {showCategories && categories.length > 0 && categoryGroups.length === 0 && subcategories.length === 0 && (
            <div className="border-b pb-2">
              <button
                onClick={() => setExpandedSections((prev) => ({ ...prev, categories: !prev.categories }))}
                className="flex items-center justify-between w-full mb-3"
              >
                <h3 className="text-base font-bold text-main group-hover:text-[var(--accent)] transition-colors uppercase tracking-tight">{t('sidebar_categories', 'Категории')}</h3>
                <svg
                  className={`w-4 h-4 text-main/40 group-hover:text-[var(--accent)] transition-transform duration-300 ${expandedSections.categories ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {expandedSections.categories && (
                <div className="space-y-2 max-h-64 overflow-y-auto custom-scrollbar">
                  {categories.map((category) => (
                    <label key={category.id} className="flex items-center space-x-3 cursor-pointer group">
                      <input
                        type="checkbox"
                        checked={filters.categories.includes(category.id)}
                        onChange={() => toggleCategoryFilter(category.id, ensureSlug(category.slug))}
                        className="w-4 h-4 text-[var(--accent)] border-[var(--border)] rounded focus:ring-[var(--accent)] transition-colors"
                        id={`direct-cat-${category.id}`}
                      />
                      <span className="text-sm text-main group-hover:text-[var(--accent)] transition-colors flex-1">
                        {getLocalizedCategoryName(category.slug, category.name, t, category.translations, router.locale)}
                      </span>
                      {category.product_count !== undefined && (
                        <span className="text-xs text-main/50 font-normal">({category.product_count})</span>
                      )}
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}

          {showSubcategories && uniqueSubcategories.length > 0 && categoryGroups.length === 0 && (
            <div className="border-b pb-2">
              <button
                onClick={() => setExpandedSections((prev) => ({ ...prev, subcategories: !prev.subcategories }))}
                className="flex items-center justify-between w-full mb-3"
              >
                <h3 className="text-base font-bold text-main group-hover:text-[var(--accent)] transition-colors uppercase tracking-tight">{t('sidebar_subcategories', 'Подкатегории')}</h3>
                <svg
                  className={`w-4 h-4 text-main/40 group-hover:text-[var(--accent)] transition-transform duration-300 ${expandedSections.subcategories ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {expandedSections.subcategories && (
                <div className="space-y-2 max-h-64 overflow-y-auto custom-scrollbar">
                  {uniqueSubcategories.map((subcategory) => (
                    <label key={subcategory.id} className="flex items-center space-x-3 cursor-pointer group">
                      <input
                        type="checkbox"
                        checked={filters.subcategories.includes(subcategory.id)}
                        onChange={() =>
                          toggleSubcategoryFilter(
                            subcategory.id,
                            categoryType === 'jewelry' ? getJewelrySubcategoryKey(subcategory) : subcategory.slug
                          )
                        }
                        className="w-4 h-4 text-[var(--accent)] border-[var(--border)] rounded focus:ring-[var(--accent)] transition-colors"
                        id={`direct-sub-${subcategory.id}`}
                      />
                      <span className="text-sm text-main group-hover:text-[var(--accent)] transition-colors flex-1">
                        {getSubcategoryLabel(subcategory)}
                      </span>
                      {subcategory.product_count !== undefined && (
                        <span className="text-xs text-main/50 font-normal">({subcategory.product_count})</span>
                      )}
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}

          {categoryType === 'books' && (bookAuthors.length > 0 || bookGenres.length > 0 || bookPublishers.length > 0 || bookLanguages.length > 0) && (
            <div className="border-b pb-2 space-y-4">
              {bookAuthors.length > 0 && (
                <div>
                <button
                  onClick={() => setExpandedSections((prev) => ({ ...prev, bookFilters: !prev.bookFilters }))}
                  className="flex items-center justify-between w-full mb-3 group"
                >
                  <h3 className="text-base font-semibold text-main group-hover:text-[var(--accent)] transition-colors">{t('sidebar_book_authors', 'Авторы')}</h3>
                  <svg
                    className={`w-5 h-5 text-main/40 group-hover:text-[var(--accent)] transition-transform duration-300 ${expandedSections.bookFilters ? 'rotate-180' : ''}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
                {expandedSections.bookFilters && (
                  <div className="space-y-2 max-h-64 overflow-y-auto custom-scrollbar">
                    {bookAuthors.map((author) => (
                      <label key={author.id} className="flex items-center space-x-3 cursor-pointer group">
                        <input
                          type="checkbox"
                          checked={filters.authorIds?.includes(author.id) || false}
                          onChange={() => toggleAuthorFilter(author.id)}
                          className="w-4 h-4 text-[var(--accent)] border-[var(--border)] rounded focus:ring-[var(--accent)] transition-colors"
                        />
                        <span className="text-sm text-main group-hover:text-[var(--accent)] transition-colors flex-1">{author.name}</span>
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
                    className="flex items-center justify-between w-full mb-3 group"
                  >
                    <h3 className="text-base font-semibold text-main group-hover:text-[var(--accent)] transition-colors">{t('sidebar_book_genres', 'Жанры')}</h3>
                    <svg
                      className={`w-5 h-5 text-main/40 group-hover:text-[var(--accent)] transition-transform duration-300 ${expandedSections.bookFilters ? 'rotate-180' : ''}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                  {expandedSections.bookFilters && (
                    <div className="space-y-2 max-h-64 overflow-y-auto custom-scrollbar">
                      {bookGenres.map((genre) => (
                        <label key={genre.id} className="flex items-center space-x-3 cursor-pointer group">
                          <input
                            type="checkbox"
                            checked={filters.genreIds?.includes(genre.id) || false}
                            onChange={() => toggleGenreFilter(genre.id)}
                            className="w-4 h-4 text-[var(--accent)] border-[var(--border)] rounded focus:ring-[var(--accent)] transition-colors"
                          />
                          <span className="text-sm text-main group-hover:text-[var(--accent)] transition-colors flex-1">
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
                    className="flex items-center justify-between w-full mb-3 group"
                  >
                    <h3 className="text-base font-semibold text-main group-hover:text-[var(--accent)] transition-colors">{t('sidebar_book_publishers', 'Издательства')}</h3>
                    <svg
                      className={`w-5 h-5 text-main/40 group-hover:text-[var(--accent)] transition-transform duration-300 ${expandedSections.bookFilters ? 'rotate-180' : ''}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                  {expandedSections.bookFilters && (
                    <div className="space-y-2 max-h-64 overflow-y-auto custom-scrollbar">
                      {bookPublishers.map((publisher) => (
                        <label key={publisher} className="flex items-center space-x-3 cursor-pointer group">
                          <input
                            type="checkbox"
                            checked={filters.publishers?.includes(publisher) || false}
                            onChange={() => togglePublisherFilter(publisher)}
                            className="w-4 h-4 text-[var(--accent)] border-[var(--border)] rounded focus:ring-[var(--accent)] transition-colors"
                          />
                          <span className="text-sm text-main group-hover:text-[var(--accent)] transition-colors flex-1">{publisher}</span>
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
                    className="flex items-center justify-between w-full mb-3 group"
                  >
                    <h3 className="text-base font-semibold text-main group-hover:text-[var(--accent)] transition-colors">{t('sidebar_book_languages', 'Язык')}</h3>
                    <svg
                      className={`w-5 h-5 text-main/40 group-hover:text-[var(--accent)] transition-transform duration-300 ${expandedSections.bookFilters ? 'rotate-180' : ''}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                  {expandedSections.bookFilters && (
                    <div className="space-y-2 max-h-64 overflow-y-auto custom-scrollbar">
                      {bookLanguages.map((language) => (
                        <label key={language} className="flex items-center space-x-3 cursor-pointer group">
                          <input
                            type="checkbox"
                            checked={filters.languages?.includes(language) || false}
                            onChange={() => toggleLanguageFilter(language)}
                            className="w-4 h-4 text-[var(--accent)] border-[var(--border)] rounded focus:ring-[var(--accent)] transition-colors"
                          />
                          <span className="text-sm text-main group-hover:text-[var(--accent)] transition-colors flex-1">{language}</span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {brandGroups.length > 0 && categoryType !== 'books' && categoryType !== 'uslugi' && (
            <div className="border-b pb-2">
              {brandGroups.map((group) => (
                <div key={group.title}>
                  <h3 className="text-base font-bold text-main mb-3 uppercase tracking-tight">{group.title}</h3>
                  <div className="space-y-2">{renderTreeItems(group.items)}</div>
                </div>
              ))}
            </div>
          )}

          {brands.length > 0 && brandGroups.length === 0 && categoryType !== 'books' && categoryType !== 'uslugi' && (
            <div className="border-b pb-2">
              <button
                onClick={() => setExpandedSections((prev) => ({ ...prev, brands: !prev.brands }))}
                className="flex items-center justify-between w-full mb-3"
              >
                <h3 className="text-base font-bold text-main group-hover:text-[var(--accent)] transition-colors uppercase tracking-tight">{t('sidebar_brands', 'Бренды')}</h3>
                <svg
                  className={`w-4 h-4 text-main/40 group-hover:text-[var(--accent)] transition-transform duration-300 ${expandedSections.brands ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {expandedSections.brands && (
                <div className="space-y-2 max-h-64 overflow-y-auto custom-scrollbar">
                  {brands.map((brand) => (
                    <label key={brand.id} className="flex items-center space-x-2 cursor-pointer group">
                      <input
                        type="checkbox"
                        checked={filters.brands.includes(brand.id)}
                        onChange={() => toggleBrandFilter(brand.id, ensureSlug(brand.slug))}
                        className="w-4 h-4 text-[var(--accent)] border-[var(--border)] rounded focus:ring-[var(--accent)]"
                      />
                      <div className="flex items-center space-x-2 flex-1">
                        <span className="text-sm text-main group-hover:text-[var(--accent)] transition-colors">
                          {getLocalizedBrandName(brand.slug, brand.name, t, brand.translations, router.locale)}
                        </span>
                      </div>
                      {brand.product_count !== undefined && (
                        <span className="text-xs text-main/50">({brand.product_count})</span>
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
              className="flex items-center justify-between w-full mb-3 group"
            >
              <h3 className="text-base font-bold text-main group-hover:text-[var(--accent)] transition-colors uppercase tracking-tight">{t('sidebar_price', 'Цена')}</h3>
              <svg
                className={`w-4 h-4 text-main/40 group-hover:text-[var(--accent)] transition-transform duration-300 ${expandedSections.price ? 'rotate-180' : ''}`}
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
                    className="w-full px-3 py-2 bg-transparent border border-[var(--border)] rounded-lg text-sm focus:ring-2 focus:ring-[var(--accent)]/20 focus:border-[var(--accent)] outline-none transition-all placeholder:text-main/30"
                  />
                  <span className="text-main/30">—</span>
                  <input
                    type="number"
                    placeholder={t('sidebar_price_to', 'До')}
                    value={priceRange.max}
                    onChange={(e) => handlePriceInputChange('max', e.target.value)}
                    onBlur={handlePriceChange}
                    className="w-full px-3 py-2 bg-transparent border border-[var(--border)] rounded-lg text-sm focus:ring-2 focus:ring-[var(--accent)]/20 focus:border-[var(--accent)] outline-none transition-all placeholder:text-main/30"
                  />
                </div>
              </div>
            )}
          </div>

          <div className="border-b pb-2">
            <h3 className="text-base font-bold text-main mb-3 uppercase tracking-tight">{t('sidebar_sort', 'Сортировка')}</h3>
            <select
              value={filters.sortBy}
              onChange={(e) => updateFilters((prev) => ({ ...prev, sortBy: e.target.value }))}
              className="w-full px-3 py-2 bg-transparent border border-[var(--border)] rounded-lg text-sm focus:ring-2 focus:ring-[var(--accent)]/20 focus:border-[var(--accent)] outline-none transition-all appearance-none cursor-pointer"
              style={{
                backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='${encodeURIComponent('rgba(59, 42, 28, 0.4)')}'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E")`,
                backgroundRepeat: 'no-repeat',
                backgroundPosition: 'right 0.75rem center',
                backgroundSize: '1rem'
              }}
            >
              <option value="name_asc">{t('sidebar_sort_name_asc_short', 'По названию (А-Я)')}</option>
              <option value="name_desc">{t('sidebar_sort_name_desc_short', 'По названию (Я-А)')}</option>
              <option value="price_asc">{t('sidebar_sort_price_asc_short', 'По цене (возрастание)')}</option>
              <option value="price_desc">{t('sidebar_sort_price_desc_short', 'По цене (убывание)')}</option>
              <option value="newest">{t('sidebar_sort_newest', 'Сначала новые')}</option>
              <option value="popular">{t('sidebar_sort_popular', 'Популярные')}</option>
            </select>
          </div>

          {categoryType !== 'uslugi' && (
            <div>
              <button
                onClick={() => setExpandedSections((prev) => ({ ...prev, filters: !prev.filters }))}
                className="flex items-center justify-between w-full mb-3 group"
              >
                <h3 className="text-base font-bold text-main group-hover:text-[var(--accent)] transition-colors uppercase tracking-tight">{t('sidebar_additional', 'Дополнительно')}</h3>
                <svg
                  className={`w-5 h-5 text-main/40 group-hover:text-[var(--accent)] transition-transform duration-300 ${expandedSections.filters ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {expandedSections.filters && (
                <div className="space-y-4">
                  <label className="flex items-center space-x-3 cursor-pointer group">
                    <input
                      type="checkbox"
                      checked={filters.inStock}
                      onChange={(e) =>
                        updateFilters((prev) => ({
                          ...prev,
                          inStock: e.target.checked
                        }))
                      }
                      className="w-4 h-4 text-[var(--accent)] border-[var(--border)] rounded focus:ring-[var(--accent)] transition-colors"
                    />
                    <span className="text-sm text-main group-hover:text-[var(--accent)] transition-colors">{t('sidebar_in_stock', 'В наличии')}</span>
                  </label>
                  <label className="flex items-center space-x-3 cursor-pointer group">
                    <input
                      type="checkbox"
                      checked={filters.isNew}
                      onChange={(e) =>
                        updateFilters((prev) => ({
                          ...prev,
                          isNew: e.target.checked
                        }))
                      }
                      className="w-4 h-4 text-[var(--accent)] border-[var(--border)] rounded focus:ring-[var(--accent)] transition-colors"
                    />
                    <span className="text-sm text-main group-hover:text-[var(--accent)] transition-colors">{t('sidebar_new', 'Новинки')}</span>
                  </label>
                </div>
              )}
            </div>
          )}
        </div>
        
        {/* Мобильная кнопка подтверждения */}
        <div className="lg:hidden sticky bottom-0 left-0 right-0 p-4 bg-[var(--bg)]/95 backdrop-blur-md border-t border-[var(--border)] shadow-[0_-10px_20px_rgba(0,0,0,0.1)]">
          <button
            onClick={onToggle}
            className="w-full py-3 bg-[var(--accent)] text-white rounded-xl font-bold hover:bg-[var(--accent-hover)] transition-all active:scale-[0.98]"
          >
            {t('sidebar_show_results', 'Показать результаты')}
          </button>
        </div>
      </aside>
    </>
  )
}
