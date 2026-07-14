import Head from 'next/head'
import Link from 'next/link'
import axios from 'axios'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/router'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useTranslation } from 'next-i18next'
import ProductCard from '../../components/ProductCard'
import CategoryHero from '../../components/CategoryHero'
import CategorySidebar, { FilterState } from '../../components/CategorySidebar'
import Pagination from '../../components/Pagination'
import { buildProductIdentityKey, isBaseProductType } from '../../lib/product'
import { buildProductUrl, getSiteOrigin } from '../../lib/urls'
import { buildCatalogPageQuery, parseCatalogFiltersQuery } from '../../lib/catalogQuery'
import { buildBrandProductsParams, brandProductsRequestKey, shouldShowGenderFilter } from '../../lib/brandCatalog'
import { ProductTranslation, BrandTranslation, getLocalizedBrandDescription, getLocalizedBrandName } from '../../lib/i18n'
import api from '../../lib/api'
import { useViewMode } from '../../hooks/useViewMode'
import { formatPrice, parsePriceWithCurrency } from '../../lib/price'

interface Product {
  id: number
  name: string
  slug: string
  description?: string
  product_type?: string
  price: string | number | null
  price_formatted?: string
  old_price?: string | number | null
  old_price_formatted?: string | null
  currency: string
  main_image?: string
  main_image_url?: string
  images?: import('../../components/ProductCardImageGallery').ProductCardGalleryImage[] | null
  video_url?: string
  main_video_url?: string
  main_gif_url?: string | null
  is_featured?: boolean
  is_new?: boolean
  translations?: ProductTranslation[]
  base_product_id?: number
  has_manual_main_image?: boolean
}

interface Category {
  id: number
  name: string
  slug: string
  description?: string
  children_count?: number
  product_count?: number
  parent?: number | null
  translations?: Array<{ locale: string; name: string; description?: string }>
}

interface Brand {
  id: number
  name: string
  slug: string
  description?: string
  products_count?: number
  primary_category_slug?: string | null
  category_slugs?: string[]
  translations?: BrandTranslation[]
}

interface BrandData {
  id: number
  name: string
  slug: string
  description: string
  translations?: BrandTranslation[]
  products: Product[]
  totalCount: number
}

interface BrandPageProps {
  brandData: BrandData
  page: number
  categories: Category[]
  initialRequestKey: string
}

const defaultFilters: FilterState = {
  categories: [],
  categorySlugs: [],
  brands: [],
  brandSlugs: [],
  subcategories: [],
  subcategorySlugs: [],
  genders: [],
  fragranceTypes: [],
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

const normalizePageParam = (value: unknown) => {
  const raw = Array.isArray(value) ? value[0] : value
  const page = Number(raw || 1)
  return Number.isFinite(page) && page > 0 ? Math.floor(page) : 1
}

const extractResults = (data: any) => {
  if (Array.isArray(data)) return data
  return data?.results || data?.data?.results || []
}

const areFilterArraysEqual = (left: Array<string | number>, right: Array<string | number>) =>
  left.length === right.length && left.every((value, index) => value === right[index])

const areFiltersEqual = (left: FilterState, right: FilterState) =>
  areFilterArraysEqual(left.categories, right.categories) &&
  areFilterArraysEqual(left.categorySlugs, right.categorySlugs) &&
  areFilterArraysEqual(left.brands, right.brands) &&
  areFilterArraysEqual(left.brandSlugs, right.brandSlugs) &&
  areFilterArraysEqual(left.subcategories, right.subcategories) &&
  areFilterArraysEqual(left.subcategorySlugs, right.subcategorySlugs) &&
  areFilterArraysEqual(left.genders || [], right.genders || []) &&
  left.priceMin === right.priceMin &&
  left.priceMax === right.priceMax &&
  left.inStock === right.inStock &&
  left.isNew === right.isNew &&
  left.sortBy === right.sortBy

export default function BrandPage(props: BrandPageProps) {
  // key: при клиентском переходе между брендами состояние (товары, фильтры,
  // страница) должно инициализироваться заново из props нового бренда.
  return <BrandPageContent key={props.brandData.slug} {...props} />
}

function BrandPageContent({
  brandData,
  page,
  categories = [],
  initialRequestKey,
}: BrandPageProps) {
  const { t, i18n } = useTranslation('common')
  const router = useRouter()
  const [viewMode, setViewMode] = useViewMode()
  const [products, setProducts] = useState<Product[]>(brandData.products || [])
  const [totalCount, setTotalCount] = useState(brandData.totalCount || 0)
  const [currentPage, setCurrentPage] = useState(Number(page) || 1)
  const [loading, setLoading] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  // Инициализация сразу из URL: первый рендер совпадает с SSR-выборкой,
  // и клиентский эффект загрузки не дублирует запрос gSSP.
  const [filters, setFilters] = useState<FilterState>(
    () => parseCatalogFiltersQuery(router.query, defaultFilters) as FilterState
  )
  const lastRequestKeyRef = useRef(initialRequestKey)
  const productsPerPage = 24
  const totalPages = Math.max(1, Math.ceil(totalCount / productsPerPage))
  const localizedBrandName = getLocalizedBrandName(brandData.slug, brandData.name, t, brandData.translations, router.locale)
  const localizedBrandDescription = getLocalizedBrandDescription(
    brandData.slug,
    brandData.description || '',
    t,
    brandData.translations,
    router.locale
  )
  const gendersKey = (filters.genders || []).join(',')
  const showGenderFilter = useMemo(
    () => shouldShowGenderFilter(categories.map((category) => category.slug)),
    [categories]
  )

  useEffect(() => {
    if (!router.isReady) return
    const nextPage = normalizePageParam(router.query.page)
    setCurrentPage((prev) => (prev === nextPage ? prev : nextPage))
    const nextFilters = parseCatalogFiltersQuery(router.query, defaultFilters) as FilterState
    setFilters((prev) => (areFiltersEqual(prev, nextFilters) ? prev : nextFilters))
  }, [router.isReady, router.asPath, router.query])

  const updatePageQuery = useCallback((
    nextPage: number,
    options: { replace?: boolean; filters?: FilterState } = {}
  ) => {
    if (!router.isReady) return
    const nextQuery = buildCatalogPageQuery(router.query, nextPage, options)
    const navigate = options.replace ? router.replace : router.push
    navigate({ pathname: router.pathname, query: nextQuery }, undefined, { shallow: true, scroll: false }).catch((error) => {
      console.error('Не удалось обновить параметры страницы бренда:', error)
    })
  }, [router])

  const resetFilters = useCallback(() => {
    setFilters(defaultFilters)
    setCurrentPage(1)
    updatePageQuery(1, { replace: true, filters: defaultFilters })
  }, [updatePageQuery])

  const handleFilterChange = useCallback((nextFilters: FilterState) => {
    setFilters(nextFilters)
    if (areFiltersEqual(filters, nextFilters)) return
    setCurrentPage(1)
    updatePageQuery(1, { replace: true, filters: nextFilters })
  }, [filters, updatePageQuery])

  const handlePageChange = (nextPage: number) => {
    const safePage = Math.min(Math.max(nextPage, 1), Math.max(totalPages, 1))
    setCurrentPage(safePage)
    updatePageQuery(safePage)
    if (typeof window !== 'undefined') {
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }

  useEffect(() => {
    if (!router.isReady || !brandData.slug) return
    const params = buildBrandProductsParams(filters, currentPage, productsPerPage)
    const requestKey = brandProductsRequestKey(brandData.slug, params)
    // SSR уже отдал эту выборку в props — не дублируем запрос на маунте.
    if (requestKey === lastRequestKeyRef.current) return
    lastRequestKeyRef.current = requestKey
    let cancelled = false

    const loadProducts = async () => {
      setLoading(true)
      try {
        const response = await api.get(`/catalog/brands/${brandData.slug}/products`, { params })
        if (cancelled) return
        const data = response.data
        setProducts(extractResults(data))
        setTotalCount(typeof data?.count === 'number' ? data.count : extractResults(data).length)
      } catch (error) {
        if (!cancelled) {
          console.error('Error loading brand products:', error)
          // Сбрасываем ключ, чтобы повторный выбор тех же фильтров сделал retry.
          lastRequestKeyRef.current = ''
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    loadProducts()
    return () => {
      cancelled = true
    }
  }, [
    router.isReady,
    brandData.slug,
    currentPage,
    filters.categories,
    filters.categorySlugs,
    gendersKey,
    filters.priceMin,
    filters.priceMax,
    filters.inStock,
    filters.isNew,
    filters.sortBy,
  ])

  if (!brandData) {
    return <div>{t('brand_not_found', 'Бренд не найден')}</div>
  }

  const siteUrl = getSiteOrigin()
  const brandPath = `/brand/${brandData.slug}`
  const localePrefix = router.locale === router.defaultLocale ? '' : `/${router.locale}`
  const canonicalUrl = `${siteUrl}${localePrefix}${brandPath}`
  const metaTitle = `${localizedBrandName} — Mudaroba`
  const metaDescription = localizedBrandDescription?.slice(0, 200) || `Товары бренда ${localizedBrandName} на Mudaroba`
  const breadcrumbs = [
    { href: '/', label: t('breadcrumb_home', 'Главная') },
    { href: '/brands', label: t('brands', 'Бренды') },
    { href: brandPath, label: localizedBrandName },
  ]

  return (
    <>
      <Head>
        <title>{metaTitle}</title>
        <meta name="description" content={metaDescription} />
        <link rel="canonical" href={canonicalUrl} />
        <link rel="alternate" hrefLang="ru" href={`${siteUrl}${brandPath}`} />
        <link rel="alternate" hrefLang="en" href={`${siteUrl}/en${brandPath}`} />
        <link rel="alternate" hrefLang="x-default" href={`${siteUrl}${brandPath}`} />
        <meta property="og:title" content={metaTitle} />
        <meta property="og:description" content={metaDescription} />
        <meta property="og:url" content={canonicalUrl} />
        <meta property="og:type" content="website" />
        <meta property="twitter:card" content="summary_large_image" />
        <meta property="twitter:title" content={metaTitle} />
        <meta property="twitter:description" content={metaDescription} />
      </Head>

      <CategoryHero
        title={localizedBrandName}
        description={localizedBrandDescription}
        totalCount={totalCount}
        categorySlug="brand"
      />

      <div className="mx-auto max-w-7xl px-3 sm:px-6 lg:px-8 pt-3 pb-0 sm:py-3 flex items-center justify-between">
        <nav className="text-sm text-main flex flex-wrap items-center gap-2">
          {breadcrumbs.map((item, idx) => {
            const isLast = idx === breadcrumbs.length - 1
            return (
              <span key={`${item.href}-${idx}`} className="flex items-center gap-2">
                {!isLast ? (
                  <Link href={item.href} className="hover:text-[var(--accent)] transition-colors">
                    {item.label}
                  </Link>
                ) : (
                  <span className="text-main font-medium">{item.label}</span>
                )}
                {!isLast && <span className="text-main/60">/</span>}
              </span>
            )
          })}
        </nav>

        <div className="hidden lg:flex items-center gap-2">
          <button
            onClick={() => setViewMode('grid')}
            className={`p-2 rounded-lg transition-colors ${viewMode === 'grid' ? 'bg-[var(--accent-soft)] text-[var(--accent)]' : 'bg-[var(--surface)] text-main hover:bg-[var(--accent-soft)]'}`}
            aria-label={t('category_view_grid', 'Сетка')}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
            </svg>
          </button>
          <button
            onClick={() => setViewMode('list')}
            className={`p-2 rounded-lg transition-colors ${viewMode === 'list' ? 'bg-[var(--accent-soft)] text-[var(--accent)]' : 'bg-[var(--surface)] text-main hover:bg-[var(--accent-soft)]'}`}
            aria-label={t('category_view_list', 'Список')}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
        </div>
      </div>

      <div className="mx-auto max-w-7xl px-3 sm:px-6 lg:px-8 pt-0 pb-8 sm:py-8">
        <div className="flex flex-col lg:flex-row gap-8">
          <div className="lg:w-80 flex-shrink-0">
            <CategorySidebar
              key={brandData.slug}
              categories={categories}
              subcategories={[]}
              onFilterChange={handleFilterChange}
              isOpen={sidebarOpen}
              onToggle={() => setSidebarOpen(!sidebarOpen)}
              initialFilters={filters}
              showCategories={categories.length > 0}
              showSubcategories={false}
              showGenderFilter={showGenderFilter}
              categoryType="brand"
            />
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex lg:hidden items-center justify-between gap-4 mb-6">
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="lg:hidden flex items-center gap-2 px-4 py-2 bg-[var(--surface)] border border-[var(--border)] rounded-lg hover:bg-[var(--accent-soft)] transition-colors text-main"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
                </svg>
                {t('sidebar_filters', 'Фильтры')}
              </button>

              <div className="flex items-center gap-2 ml-auto">
                <button
                  onClick={() => setViewMode('grid')}
                  className={`p-2 rounded-lg transition-colors ${viewMode === 'grid' ? 'bg-[var(--accent-soft)] text-[var(--accent)]' : 'bg-[var(--surface)] text-main hover:bg-[var(--accent-soft)]'}`}
                  aria-label={t('category_view_grid', 'Сетка')}
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
                  </svg>
                </button>
                <button
                  onClick={() => setViewMode('list')}
                  className={`p-2 rounded-lg transition-colors ${viewMode === 'list' ? 'bg-[var(--accent-soft)] text-[var(--accent)]' : 'bg-[var(--surface)] text-main hover:bg-[var(--accent-soft)]'}`}
                  aria-label={t('category_view_list', 'Список')}
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                  </svg>
                </button>
              </div>
            </div>

            {loading && products.length === 0 ? (
              <div className="flex items-center justify-center py-20">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-violet-600"></div>
              </div>
            ) : products.length > 0 ? (
              <>
                <div
                  className={
                    (viewMode === 'grid'
                      ? 'grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-6 mb-8'
                      : 'space-y-4 mb-8') +
                    (loading ? ' opacity-40 pointer-events-none transition-opacity duration-150' : ' transition-opacity duration-150')
                  }
                >
                  {products.map((product) => {
                    const effectiveProductType = (product.product_type || 'medicines').replace(/_/g, '-')
                    const isBaseProduct = isBaseProductType(effectiveProductType)
                    const parsedPrice = parsePriceWithCurrency(product.price_formatted ?? product.price)
                    const parsedOldPrice = parsePriceWithCurrency(product.old_price_formatted ?? product.old_price)
                    const displayCurrency = parsedPrice.currency || product.currency
                    const displayPrice = formatPrice(parsedPrice.price, displayCurrency, i18n.language)
                    const displayOldPrice =
                      !parsedOldPrice.currency || parsedOldPrice.currency === displayCurrency
                        ? formatPrice(parsedOldPrice.price, displayCurrency, i18n.language)
                        : null
                    return (
                      <ProductCard
                        key={buildProductIdentityKey(product, effectiveProductType)}
                        id={product.id}
                        baseProductId={product.base_product_id}
                        name={product.name}
                        slug={product.slug}
                        price={displayPrice}
                        currency={displayCurrency}
                        oldPrice={displayOldPrice}
                        imageUrl={product.main_image_url || product.main_image}
                        galleryImages={product.images}
                        videoUrl={product.video_url}
                        mainVideoUrl={product.main_video_url}
                        mainGifUrl={product.main_gif_url}
                        hasManualMainImage={product.has_manual_main_image}
                        badge={product.is_featured ? t('product_featured', 'Хит') : null}
                        viewMode={viewMode}
                        description={product.description}
                        href={buildProductUrl(effectiveProductType, product.slug)}
                        productType={effectiveProductType}
                        isBaseProduct={isBaseProduct}
                        translations={product.translations}
                        locale={i18n.language}
                        isNew={product.is_new}
                        isFeatured={product.is_featured}
                      />
                    )
                  })}
                </div>

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
                <h3 className="text-2xl font-semibold text-main mb-2">
                  {t('products_not_found', 'Товары не найдены')}
                </h3>
                <p className="text-main/80 mb-6">
                  {t('products_not_found_description', 'Попробуйте изменить параметры фильтров')}
                </p>
                <button
                  onClick={resetFilters}
                  className="px-6 py-3 bg-accent text-white rounded-lg hover:bg-[var(--accent-strong)] transition-colors"
                >
                  {t('reset_filters', 'Сбросить фильтры')}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}

export async function getServerSideProps(ctx: any) {
  ctx.res.setHeader('Cache-Control', 'public, s-maxage=300, stale-while-revalidate=86400')
  ctx.res.setHeader('Vary', 'Cookie, Accept-Language')
  try {
    const { slug } = ctx.params
    const page = normalizePageParam(ctx.query?.page)
    const pageSize = 24
    const { getInternalApiUrl } = await import('../../lib/urls')
    const slugValue = Array.isArray(slug) ? slug[0] : String(slug || '')

    const brandRes = await axios.get(getInternalApiUrl(`catalog/brands/${encodeURIComponent(slugValue)}`))
    const brand: Brand = brandRes.data

    const filters = parseCatalogFiltersQuery(ctx.query || {}, defaultFilters) as FilterState
    const productParams = buildBrandProductsParams(filters, page, pageSize)
    const cookieHeader: string = ctx.req.headers.cookie || ''
    const currencyMatch = cookieHeader.match(/(?:^|;\s*)currency=([^;]+)/)
    const currency = currencyMatch ? decodeURIComponent(currencyMatch[1]).toUpperCase() : 'RUB'

    const [productsRes, categoriesRes] = await Promise.all([
      axios.get(getInternalApiUrl(`catalog/brands/${brand.slug}/products`), {
        params: productParams,
        headers: {
          'X-Currency': currency,
          'Accept-Language': ctx.locale || 'en',
        },
      }),
      // Категории бренда — некритичны для первого экрана: при ошибке сайдбар
      // просто останется без секции категорий.
      axios.get(getInternalApiUrl(`catalog/brands/${brand.slug}/categories`)).catch(() => null),
    ])
    const productsData = productsRes.data
    const products = extractResults(productsData)
    const totalCount = typeof productsData?.count === 'number' ? productsData.count : products.length
    const categories: Category[] = categoriesRes ? extractResults(categoriesRes.data) : []

    return {
      props: {
        ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])),
        brandData: {
          id: brand.id,
          name: brand.name,
          slug: brand.slug,
          description: brand.description || '',
          translations: brand.translations || [],
          products,
          totalCount,
        },
        page,
        categories,
        initialRequestKey: brandProductsRequestKey(brand.slug, productParams),
      },
    }
  } catch (e) {
    if (axios.isAxiosError(e) && e.response?.status === 404) {
      return { notFound: true }
    }
    throw e
  }
}
