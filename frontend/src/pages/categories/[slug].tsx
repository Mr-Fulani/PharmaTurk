import Head from 'next/head'
import { useRouter } from 'next/router'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useTranslation } from 'next-i18next'
import { GetServerSideProps } from 'next'
import { useState, useEffect, useMemo } from 'react'
import axios from 'axios'
import { getApiForCategory } from '../../lib/api'
import ProductCard from '../../components/ProductCard'
import CategorySidebar, { FilterState, SidebarTreeItem, SidebarTreeSection } from '../../components/CategorySidebar'
import Pagination from '../../components/Pagination'

interface Product {
  id: number
  name: string
  slug: string
  description: string
  price: number
  price_formatted: string
  old_price?: number
  old_price_formatted?: string
  currency: string
  final_price_rub?: number
  final_price_usd?: number
  main_image?: string
  main_image_url?: string
  is_available: boolean
  is_featured: boolean
  category?: {
    id: number
    name: string
    slug: string
  }
  brand?: {
    id: number
    name: string
    slug: string
  }
  size?: string
  color?: string
  material?: string
  season?: string
  heel_height?: string
  sole_type?: string
  model?: string
  specifications?: any
  warranty?: string
  power_consumption?: string
}

interface Category {
  id: number
  name: string
  slug: string
  description: string
  children_count: number
  product_count?: number
  gender?: string
  gender_display?: string
  clothing_type?: string
  shoe_type?: string
  device_type?: string
}

interface Brand {
  id: number
  name: string
  slug: string
  description: string
  logo?: string
  product_count?: number
}

interface CategoryPageProps {
  products: Product[]
  categories: Category[]
  brands: Brand[]
  subcategories?: Category[]
  categoryName: string
  categoryDescription?: string
  totalCount: number
  currentPage: number
  totalPages: number
  categoryType: 'medicines' | 'clothing' | 'shoes' | 'electronics' | 'supplements' | 'tableware' | 'furniture' | 'medical-equipment'
}

type CategoryTypeKey = CategoryPageProps['categoryType']

const brandProductTypeMap: Record<CategoryTypeKey, 'medicines' | 'clothing' | 'shoes' | 'electronics' | 'tableware' | 'furniture' | 'medical-equipment'> = {
  medicines: 'medicines',
  supplements: 'medicines',
  clothing: 'clothing',
  shoes: 'shoes',
  electronics: 'electronics',
  tableware: 'tableware',
  furniture: 'furniture',
  'medical-equipment': 'medical-equipment'
}

const resolveBrandProductType = (type: CategoryTypeKey) => brandProductTypeMap[type] || 'medicines'

const createTreeItem = (category: Category): SidebarTreeItem => ({
  id: `cat-${category.id}`,
  name: category.name,
  slug: category.slug,
  dataId: category.id,
  count: category.product_count,
  type: 'category'
})

const fallbackGenderItems: Record<string, string[]> = {
  male: ['Футболки', 'Рубашки', 'Штаны', 'Костюмы'],
  female: ['Блузки', 'Платья', 'Кофты', 'Юбки'],
  kids: ['Футболки', 'Шорты', 'Комбинезоны']
}

const clothingGenderKeywords: Record<string, string[]> = {
  male: ['male', 'men', 'муж', 'мужская'],
  female: ['female', 'women', 'жен', 'женская'],
  kids: ['kids', 'children', 'дет', 'детская']
}

const createFallbackItems = (_items: string[]): SidebarTreeItem[] => []

const buildClothingSections = (categories: Category[]): SidebarTreeSection[] => {
  const sections = [
    { key: 'male', title: 'Мужская одежда' },
    { key: 'female', title: 'Женская одежда' },
    { key: 'kids', title: 'Детская одежда' }
  ]

  return sections.map(({ key, title }) => {
    const keywords = clothingGenderKeywords[key] || []
    const children = categories
      .filter((category) =>
        keywords.some((keyword) => category.slug.includes(keyword) || category.name.toLowerCase().includes(keyword))
      )
      .map((category) => createTreeItem(category))

    return {
      title,
      items: children.length > 0 ? children : createFallbackItems(fallbackGenderItems[key] || [])
    }
  })

}
const medicineKeywordGroups = [
  { label: 'Обезболивающие', keywords: ['pain', 'обезбол'] },
  { label: 'Антибиотики', keywords: ['antibiotic', 'антибиот'] },
  { label: 'Витамины и иммунитет', keywords: ['vitamin', 'витамин'] },
  { label: 'Гинекология', keywords: ['gynec', 'гинек'] },
  { label: 'Онкология', keywords: ['oncology', 'онколо', 'рак'] }
]

const buildMedicineSections = (categories: Category[]): SidebarTreeSection[] =>
  medicineKeywordGroups.map((group) => {
    const children: SidebarTreeItem[] = categories
      .filter((category) =>
        group.keywords.some((keyword) => category.slug.includes(keyword) || category.name.toLowerCase().includes(keyword))
      )
      .map((category) => ({
        id: `med-${category.id}`,
        name: category.name,
        slug: category.slug,
        dataId: category.id,
        count: category.product_count,
        type: 'category'
      }))

    return {
      title: group.label,
      items: children.length > 0 ? children : createFallbackItems([group.label])
    }
  })

const getCategorySections = (type: CategoryPageProps['categoryType'], categories: Category[]): SidebarTreeSection[] => {
  if (type === 'clothing') {
    return buildClothingSections(categories)
  }
  if (type === 'medicines') {
    return buildMedicineSections(categories)
  }
  return []
}

export default function CategoryPage({
  products: initialProducts,
  categories,
  brands,
  subcategories = [],
  categoryName,
  categoryDescription,
  totalCount: initialTotalCount,
  currentPage: initialCurrentPage,
  totalPages: initialTotalPages,
  categoryType
}: CategoryPageProps) {
  const { t } = useTranslation('common')
  const router = useRouter()
  const { slug } = router.query

  const [products, setProducts] = useState(initialProducts)
  const [totalCount, setTotalCount] = useState(initialTotalCount)
  const [currentPage, setCurrentPage] = useState(initialCurrentPage)
  const [totalPages, setTotalPages] = useState(initialTotalPages)
  const [loading, setLoading] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  const [brandOptions, setBrandOptions] = useState(brands)
  const [filters, setFilters] = useState<FilterState>({
    categories: [],
    categorySlugs: [],
    brands: [],
    brandSlugs: [],
    subcategories: [],
    subcategorySlugs: [],
    inStock: false,
    sortBy: 'name_asc'
  })
  const categoryGroups = useMemo(() => getCategorySections(categoryType, categories), [categoryType, categories])
  const resolvedBrandType = useMemo(() => resolveBrandProductType(categoryType), [categoryType])

  useEffect(() => {
    setBrandOptions(brands)
  }, [brands])

  useEffect(() => {
    const loadBrands = async () => {
      try {
        const params: Record<string, any> = {
          product_type: resolvedBrandType
        }
        if (filters.categories.length > 0) {
          params.category_id = filters.categories
        } else if (filters.categorySlugs.length > 0) {
          params.category_slug = filters.categorySlugs.join(',')
        }
        if (filters.inStock) {
          params.in_stock = true
        }
        const base = process.env.NEXT_PUBLIC_API_BASE || '/api'
        const response = await axios.get(`${base}/catalog/brands`, { params })
        const list = Array.isArray(response.data) ? response.data : response.data.results || []
        setBrandOptions(list)
        setFilters((prev) => {
          const allowedIds = new Set(list.map((brand: any) => brand.id))
          const allowedSlugs = new Set(list.map((brand: any) => brand.slug))
          const nextBrandIds = prev.brands.filter((id) => allowedIds.has(id))
          const nextBrandSlugs = prev.brandSlugs.filter((slug) => !slug || allowedSlugs.has(slug))
          if (nextBrandIds.length === prev.brands.length && nextBrandSlugs.length === prev.brandSlugs.length) {
            return prev
          }
          return {
            ...prev,
            brands: nextBrandIds,
            brandSlugs: nextBrandSlugs
          }
        })
      } catch (error) {
        console.error('Error loading brands:', error)
      }
    }

    loadBrands()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedBrandType, filters.categories, filters.categorySlugs, filters.inStock])

  // Загрузка товаров с фильтрами
  useEffect(() => {
    const loadProducts = async () => {
      setLoading(true)
      try {
        const params: any = {
          page: currentPage,
          page_size: 12
        }

        if (filters.categories.length > 0) {
          params.category_id = filters.categories
        }
        if (filters.categorySlugs.length > 0) {
          params.category_slug = filters.categorySlugs.join(',')
        }
        if (filters.brands.length > 0) {
          params.brand_id = filters.brands
        }
        if (filters.brandSlugs.length > 0) {
          params.brand_slug = filters.brandSlugs.join(',')
        }
        if (filters.subcategories.length > 0) {
          params.subcategory_id = filters.subcategories
        }
        if (filters.subcategorySlugs.length > 0) {
          params.subcategory_slug = filters.subcategorySlugs.join(',')
        }
        if (filters.priceMin !== undefined) {
          params.price_min = filters.priceMin
        }
        if (filters.priceMax !== undefined) {
          params.price_max = filters.priceMax
        }
        if (filters.inStock) {
          params.in_stock = true
        }
        if (filters.sortBy) {
          params.ordering = filters.sortBy
        }

        const base = process.env.NEXT_PUBLIC_API_BASE || '/api'
        const api = getApiForCategory(categoryType)
        
        const response = await api.getProducts(params)
        const data = response.data
        const productsList = Array.isArray(data) ? data : (data.results || [])
        const count = data.count || productsList.length

        setProducts(productsList)
        setTotalCount(count)
        setTotalPages(Math.ceil(count / 12))
      } catch (error) {
        console.error('Error loading products:', error)
      } finally {
        setLoading(false)
      }
    }

    loadProducts()
  }, [filters, currentPage, categoryType])

  const handlePageChange = (page: number) => {
    setCurrentPage(page)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleFilterChange = (newFilters: FilterState) => {
    setFilters(newFilters)
    setCurrentPage(1)
  }

  const getCategoryColor = () => {
    const colors: Record<string, string> = {
      medicines: 'from-green-600 to-emerald-500',
      supplements: 'from-amber-600 to-yellow-500',
      clothing: 'from-rose-600 to-pink-500',
      shoes: 'from-blue-600 to-indigo-500',
      electronics: 'from-slate-700 to-gray-600',
      tableware: 'from-orange-600 to-red-500',
      furniture: 'from-amber-800 to-orange-700',
      'medical-equipment': 'from-teal-600 to-cyan-500'
    }
    return colors[categoryType] || 'from-violet-600 to-purple-500'
  }

  return (
    <>
      <Head>
        <title>{categoryName} - PharmaTurk</title>
        <meta name="description" content={categoryDescription || `Каталог ${categoryName.toLowerCase()} в PharmaTurk`} />
      </Head>
      
      {/* Hero Section */}
      <div className={`bg-gradient-to-r ${getCategoryColor()} text-white py-12`}>
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-4xl md:text-5xl font-bold mb-4">{categoryName}</h1>
              {categoryDescription && (
                <p className="text-lg md:text-xl opacity-90 max-w-2xl">{categoryDescription}</p>
              )}
              <p className="mt-4 text-sm opacity-80">
                Найдено товаров: <span className="font-semibold">{totalCount}</span>
              </p>
            </div>
          </div>
        </div>
        </div>

      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex flex-col lg:flex-row gap-8">
          {/* Sidebar */}
          <div className="lg:w-1/4">
            <CategorySidebar
              categories={categoryGroups.length > 0 ? [] : categories}
              brands={brandOptions}
              subcategories={subcategories}
              categoryGroups={categoryGroups}
              onFilterChange={handleFilterChange}
              isOpen={sidebarOpen}
              onToggle={() => setSidebarOpen(!sidebarOpen)}
            />
          </div>

          {/* Main Content */}
          <div className="lg:w-3/4">
            {/* Toolbar */}
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
              {/* Mobile filter button */}
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="lg:hidden flex items-center gap-2 px-4 py-2 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
                </svg>
                Фильтры
              </button>

              {/* View mode toggle */}
              <div className="flex items-center gap-2 ml-auto">
                <button
                  onClick={() => setViewMode('grid')}
                  className={`p-2 rounded-lg transition-colors ${
                    viewMode === 'grid'
                      ? 'bg-violet-100 text-violet-700'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                  aria-label="Grid view"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
                  </svg>
                </button>
                  <button
                  onClick={() => setViewMode('list')}
                  className={`p-2 rounded-lg transition-colors ${
                    viewMode === 'list'
                      ? 'bg-violet-100 text-violet-700'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                  aria-label="List view"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                  </svg>
                  </button>
              </div>
            </div>

            {/* Products */}
            {loading ? (
              <div className="flex items-center justify-center py-20">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-violet-600"></div>
              </div>
            ) : products.length > 0 ? (
              <>
                <div
                  className={
                    viewMode === 'grid'
                      ? 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 mb-8'
                      : 'space-y-4 mb-8'
                  }
                >
                  {products.map((product) => {
                    // Используем final_price_rub если доступно, иначе оригинальную цену
                    const displayPrice = product.final_price_rub ?? product.price
                    const displayCurrency = product.final_price_rub ? 'RUB' : product.currency
                    const displayOldPrice = product.old_price ? String(product.old_price) : null
                    const productHref = `/product/${categoryType}/${product.slug}`
                    const isBaseProductType = ['medicines', 'supplements', 'medical-equipment'].includes(categoryType)
                    
                    return (
                      <ProductCard
                        key={product.id}
                        id={product.id}
                        name={product.name}
                        slug={product.slug}
                        price={displayPrice ? String(displayPrice) : null}
                        currency={displayCurrency}
                        oldPrice={displayOldPrice}
                        imageUrl={product.main_image_url || product.main_image}
                        badge={product.is_featured ? 'Хит' : null}
                        viewMode={viewMode}
                        description={product.description}
                        href={productHref}
                        productType={categoryType}
                        isBaseProduct={isBaseProductType}
                      />
                    )
                  })}
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                  <Pagination
                    currentPage={currentPage}
                    totalPages={totalPages}
                    onPageChange={handlePageChange}
                  />
                )}
              </>
            ) : (
              <div className="text-center py-20">
                <div className="text-6xl mb-4">😔</div>
                <h3 className="text-2xl font-semibold text-gray-900 mb-2">
                  Товары не найдены
                </h3>
                <p className="text-gray-600 mb-6">
                  Попробуйте изменить параметры фильтров или выберите другую категорию
                </p>
                <button
                  onClick={() => {
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
                    setCurrentPage(1)
                  }}
                  className="px-6 py-3 bg-violet-600 text-white rounded-lg hover:bg-violet-700 transition-colors"
                >
                  Сбросить фильтры
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}

// Сохраняем оригинальную getServerSideProps для совместимости
export const getServerSideProps: GetServerSideProps = async (context) => {
  const { slug, page = 1, brand } = context.query
  const pageSize = 12

  try {
    let categoryType: CategoryTypeKey = 'medicines'
    
    const categoryMap: Record<string, CategoryTypeKey> = {
      medicines: 'medicines',
      supplements: 'supplements',
      clothing: 'clothing',
      shoes: 'shoes',
      electronics: 'electronics',
      tableware: 'tableware',
      furniture: 'furniture',
      'medical-equipment': 'medical-equipment'
    }

    categoryType = categoryMap[slug as string] || 'medicines'

    const api = getApiForCategory(categoryType)
    const base = process.env.INTERNAL_API_BASE || 'http://backend:8000'

    const brandSlug = Array.isArray(brand) ? brand[0] : brand
    const brandProductType = resolveBrandProductType(categoryType)

    if (categoryType === 'medicines') {
      const brandRes = await axios
        .get(`${base}/api/catalog/brands`, { params: { product_type: brandProductType } })
        .catch(() => ({ data: { results: [] } }))
      const brands = brandRes.data.results || []

      const productParams: Record<string, any> = { page, page_size: pageSize }
      if (brandSlug) {
        const selectedBrand = brands.find((b: any) => b.slug === brandSlug)
        if (selectedBrand) {
          productParams.brand_id = selectedBrand.id
        }
      }

      const prodRes = await axios.get(`${base}/api/catalog/products`, {
        params: productParams
      })
      const productsData = prodRes.data
      let products = Array.isArray(productsData) ? productsData : (productsData.results || [])
      const totalCount = prodRes.data.count || products.length
      
      const categories = [
        { id: 1, name: 'Обезболивающие', slug: 'painkillers', children_count: 0 },
        { id: 2, name: 'Антибиотики', slug: 'antibiotics', children_count: 0 },
        { id: 3, name: 'Витамины', slug: 'vitamins', children_count: 0 },
        { id: 4, name: 'БАДы', slug: 'supplements', children_count: 0 }
      ]
      
      return {
        props: {
          products,
          categories,
          brands,
          subcategories: [],
          categoryName: 'Медикаменты',
          categoryDescription: 'Лекарственные препараты и медикаменты из Турции',
          totalCount,
          currentPage: Number(page),
          totalPages: Math.ceil(totalCount / pageSize),
          categoryType,
          ...(await serverSideTranslations(context.locale ?? 'en', ['common'])),
        },
      }
    } else {
      const brandRes = await axios
        .get(`${base}/api/catalog/brands`, { params: { product_type: brandProductType } })
        .catch(() => ({ data: { results: [] } }))
      const brands = brandRes.data.results || []

      const productParams: any = { page, page_size: pageSize }
      if (brandSlug) {
        const selectedBrand = brands.find((b: any) => b.slug === brandSlug)
        if (selectedBrand) {
          productParams.brand_id = selectedBrand.id
        }
      }

      const [prodRes, catRes] = await Promise.all([
        axios
          .get(`${base}/api/catalog/${categoryType}/products`, {
            params: productParams
          })
          .catch(() => ({ data: { results: [], count: 0 } })),
        axios.get(`${base}/api/catalog/${categoryType}/categories`).catch(() => ({ data: { results: [] } }))
      ])

      const productsData = prodRes.data
      const products = Array.isArray(productsData) ? productsData : (productsData.results || [])
      const categories = catRes.data.results || []
      const totalCount = productsData.count || products.length
      
      const categoryNames: Record<string, { name: string; description: string }> = {
        clothing: { name: 'Одежда', description: 'Модная одежда для всей семьи из Турции' },
        shoes: { name: 'Обувь', description: 'Качественная обувь для всей семьи' },
        electronics: { name: 'Электроника', description: 'Современные гаджеты и техника' },
        supplements: { name: 'БАДы', description: 'Биологически активные добавки' },
        tableware: { name: 'Посуда', description: 'Кухонная посуда и аксессуары' },
        furniture: { name: 'Мебель', description: 'Мебель для дома и офиса' },
        'medical-equipment': { name: 'Медицинский инвентарь', description: 'Инструменты и оборудование для медицины' }
      }

      const categoryInfo = categoryNames[categoryType] || { name: 'Товары', description: '' }

      return {
        props: {
          products,
          categories,
          brands,
          subcategories: [],
          categoryName: categoryInfo.name,
          categoryDescription: categoryInfo.description,
          totalCount,
          currentPage: Number(page),
          totalPages: Math.ceil(totalCount / pageSize),
          categoryType,
          ...(await serverSideTranslations(context.locale ?? 'en', ['common'])),
        },
      }
    }
  } catch (error) {
    console.error('Error fetching data:', error)
    
    return {
      props: {
        products: [],
        categories: [],
        brands: [],
        subcategories: [],
        categoryName: 'Товары',
        categoryDescription: '',
        totalCount: 0,
        currentPage: 1,
        totalPages: 1,
        categoryType: 'medicines',
        ...(await serverSideTranslations(context.locale ?? 'en', ['common'])),
      },
    }
  }
}
