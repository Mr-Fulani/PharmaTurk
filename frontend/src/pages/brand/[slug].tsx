import Head from 'next/head'
import Link from 'next/link'
import axios from 'axios'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import ProductCard from '../../components/ProductCard'
import Sidebar from '../../components/Sidebar'
import { isBaseProductType } from '../../lib/product'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useTranslation } from 'next-i18next'
import { ProductTranslation } from '../../lib/i18n'

interface Product {
  id: number
  name: string
  slug: string
  price: string | null
  price_formatted?: string
  old_price?: string | number | null
  old_price_formatted?: string
  currency: string
  main_image_url?: string
  video_url?: string
  main_video_url?: string
  meta_title?: string | null
  meta_description?: string | null
  meta_keywords?: string | null
  og_title?: string | null
  og_description?: string | null
  og_image_url?: string | null
  translations?: ProductTranslation[]
}

interface Category {
  id: number
  name: string
  slug: string
  count?: number
}

interface Brand {
  id: number
  name: string
  count?: number
}

interface BrandData {
  name: string
  description: string
  products: Product[]
  totalCount: number
}

export default function BrandPage({
  brandData,
  page,
  categories = [],
  brands = []
}: {
  brandData: BrandData
  page: number
  categories: Category[]
  brands: Brand[]
}) {
  const { t, i18n } = useTranslation('common')
  const router = useRouter()
  const { slug } = router.query
  const [selectedCategory, setSelectedCategory] = useState<number | null>(null)
  const [selectedBrand, setSelectedBrand] = useState<number | null>(null)
  const [sortBy, setSortBy] = useState('name_asc')
  const [inStockOnly, setInStockOnly] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const productsPerPage = 24
  const currentPage = Number(page) || 1
  const totalPages = Math.max(1, Math.ceil((Number(brandData?.totalCount) || 0) / productsPerPage))
  const siteUrl = (process.env.NEXT_PUBLIC_SITE_URL || 'https://mudaroba.com').replace(/\/$/, '')
  const canonicalUrl = `${siteUrl}/brand/${slug || ''}`
  const metaTitle = brandData ? `${brandData.name} — Mudaroba` : 'Бренд — Mudaroba'
  const metaDescription =
    brandData?.description?.slice(0, 200) ||
    `Товары бренда ${brandData?.name || ''} на Mudaroba`
  const breadcrumbSchema = {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: [
      { '@type': 'ListItem', position: 1, name: 'Главная', item: `${siteUrl}/` },
      { '@type': 'ListItem', position: 2, name: brandData?.name || 'Бренд', item: canonicalUrl },
    ],
  }

  const goToPage = (nextPage: number) => {
    const p = Math.min(Math.max(1, nextPage), totalPages)
    router.push(
      { pathname: `/brand/${slug}`, query: { ...router.query, page: p } },
      undefined,
      { scroll: false }
    )
  }

  // Сохранение и восстановление позиции скролла при возврате на страницу
  useEffect(() => {
    if (typeof window === 'undefined') return

    const scrollKey = `scroll_${router.asPath}`
    let shouldRestoreScroll = false

    // Сохраняем позицию скролла при уходе со страницы
    const handleRouteChangeStart = (url: string) => {
      if (url !== router.asPath) {
        sessionStorage.setItem(scrollKey, String(window.scrollY))
      }
    }

    const handleRouteChangeComplete = (url: string) => {
      if (url === router.asPath) {
        shouldRestoreScroll = true
        const savedScroll = sessionStorage.getItem(scrollKey)
        if (savedScroll) {
          const scrollY = parseInt(savedScroll, 10)
          // Используем requestAnimationFrame для восстановления после рендера
          requestAnimationFrame(() => {
            requestAnimationFrame(() => {
              window.scrollTo({ top: scrollY, behavior: 'auto' })
            })
          })
        }
      }
    }

    const handleBeforeUnload = () => {
      sessionStorage.setItem(scrollKey, String(window.scrollY))
    }

    const handleVisibilityChange = () => {
      if (document.hidden) {
        sessionStorage.setItem(scrollKey, String(window.scrollY))
      } else if (shouldRestoreScroll) {
        const savedScroll = sessionStorage.getItem(scrollKey)
        if (savedScroll) {
          const scrollY = parseInt(savedScroll, 10)
          requestAnimationFrame(() => {
            requestAnimationFrame(() => {
              window.scrollTo({ top: scrollY, behavior: 'auto' })
            })
          })
        }
      }
    }

    // Восстанавливаем позицию скролла при монтировании (если это возврат на страницу)
    const savedScroll = sessionStorage.getItem(scrollKey)
    if (savedScroll && router.isReady) {
      const scrollY = parseInt(savedScroll, 10)
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          window.scrollTo({ top: scrollY, behavior: 'auto' })
        })
      })
    }

    router.events.on('routeChangeStart', handleRouteChangeStart)
    router.events.on('routeChangeComplete', handleRouteChangeComplete)
    window.addEventListener('beforeunload', handleBeforeUnload)
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      router.events.off('routeChangeStart', handleRouteChangeStart)
      router.events.off('routeChangeComplete', handleRouteChangeComplete)
      window.removeEventListener('beforeunload', handleBeforeUnload)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [router.asPath, router.isReady, router.events])

  if (!brandData) {
    return <div>Бренд не найден</div>
  }

  return (
    <>
      <Head>
        <title>{metaTitle}</title>
        <meta name="description" content={metaDescription} />
        <link rel="canonical" href={canonicalUrl} />
        <link rel="alternate" hrefLang="ru" href={canonicalUrl} />
        <meta property="og:title" content={metaTitle} />
        <meta property="og:description" content={metaDescription} />
        <meta property="og:url" content={canonicalUrl} />
        <meta property="og:type" content="website" />
        <meta property="twitter:card" content="summary_large_image" />
        <meta property="twitter:title" content={metaTitle} />
        <meta property="twitter:description" content={metaDescription} />
        <script
          type="application/ld+json"
          // eslint-disable-next-line react/no-danger
          dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbSchema) }}
        />
      </Head>
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-3 sm:px-6 md:flex-row">
        {/* Sidebar */}
        <div className="hidden md:block mt-6">
          <Sidebar
            categories={categories}
            brands={brands}
            onCategoryChange={setSelectedCategory}
            onBrandChange={setSelectedBrand}
            onSortChange={setSortBy}
            onAvailabilityChange={setInStockOnly}
            selectedCategory={selectedCategory}
            selectedBrand={selectedBrand}
            sortBy={sortBy}
            inStockOnly={inStockOnly}
            isOpen={true}
            onToggle={() => { }}
          />
        </div>

        {/* Mobile Sidebar */}
        <div className="md:hidden">
          <Sidebar
            categories={categories}
            brands={brands}
            onCategoryChange={setSelectedCategory}
            onBrandChange={setSelectedBrand}
            onSortChange={setSortBy}
            onAvailabilityChange={setInStockOnly}
            selectedCategory={selectedCategory}
            selectedBrand={selectedBrand}
            sortBy={sortBy}
            inStockOnly={inStockOnly}
            isOpen={sidebarOpen}
            onToggle={() => setSidebarOpen(!sidebarOpen)}
          />
        </div>

        {/* Main Content */}
        <main className="flex-1 px-3 pt-0 pb-4 sm:p-6">
          {/* Mobile sidebar toggle */}
          <div className="md:hidden mb-4">
            <button
              onClick={() => setSidebarOpen(true)}
              className="flex items-center space-x-2 px-4 py-2 bg-violet-600 text-white rounded-md hover:bg-violet-700 transition-colors duration-200"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
              <span>Фильтры</span>
            </button>
          </div>

          {/* Brand Header */}
          <div className="mb-8">
            <nav className="mb-4">
              <Link href="/" className="text-violet-600 hover:text-violet-800 text-sm">
                Главная
              </Link>
              <span className="mx-2 text-gray-400">/</span>
              <span className="text-gray-600 text-sm">{brandData.name}</span>
            </nav>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">{brandData.name}</h1>
            <p className="text-gray-600">{brandData.description}</p>
          </div>

          <div className="mt-2 w-full">
            <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-3 gap-3 sm:gap-7">
              {brandData.products.map((p) => {
                const pt = (p as { product_type?: string }).product_type || 'medicines'
                return (
                  <ProductCard
                    key={p.id}
                    id={p.id}
                    baseProductId={(p as { base_product_id?: number }).base_product_id}
                    name={p.name}
                    slug={p.slug}
                    price={p.price}
                    currency={p.currency}
                    imageUrl={p.main_image_url}
                    videoUrl={p.main_video_url || p.video_url}
                    productType={pt}
                    isBaseProduct={isBaseProductType(pt)}
                    isNew={(p as { is_new?: boolean }).is_new}
                    isFeatured={(p as { is_featured?: boolean }).is_featured}
                    translations={p.translations}
                    locale={i18n.language}
                  />
                )
              })}
            </div>

            {brandData.products.length === 0 && (
              <div className="text-center py-16">
                <h3 className="text-xl font-medium text-gray-900 mb-2">Товары не найдены</h3>
                <p className="text-gray-600">В данный момент товары этого бренда недоступны</p>
              </div>
            )}

            {totalPages > 1 && (
              <div className="flex justify-center mt-10">
                <div className="flex space-x-2">
                  <button
                    onClick={() => goToPage(currentPage - 1)}
                    disabled={currentPage <= 1}
                    className="px-4 py-2 text-sm font-medium text-gray-600 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200"
                  >
                    {t('pagination_back', 'Назад')}
                  </button>
                  {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                    <button
                      key={p}
                      onClick={() => goToPage(p)}
                      className={`px-4 py-2 text-sm font-medium rounded-md transition-colors duration-200 ${currentPage === p ? 'bg-violet-600 text-white' : 'text-gray-700 bg-white border border-gray-300 hover:bg-gray-50'}`}
                    >
                      {p}
                    </button>
                  ))}
                  <button
                    onClick={() => goToPage(currentPage + 1)}
                    disabled={currentPage >= totalPages}
                    className="px-4 py-2 text-sm font-medium text-gray-600 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200"
                  >
                    {t('pagination_forward', 'Вперед')}
                  </button>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </>
  )
}

export async function getServerSideProps(ctx: any) {
  try {
    const { slug } = ctx.params
    const page = Number(ctx.query?.page || 1)
    const pageSize = 24
    const { getInternalApiUrl } = await import('../../lib/urls')
    const slugValue = Array.isArray(slug) ? slug[0] : String(slug || '')

    let allBrands: any[] = []
    let nextUrl: string | null = getInternalApiUrl('catalog/brands?page_size=200')
    while (nextUrl) {
      const res = await axios.get(nextUrl)
      const data = res.data
      const pageBrands = Array.isArray(data) ? data : data.results || []
      allBrands = [...allBrands, ...pageBrands]
      nextUrl = data.next || null
    }

    const brand = allBrands.find((item) => item.slug === slugValue)
    if (!brand) {
      return {
        props: {
          ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])),
          brandData: null,
          page,
          categories: [],
          brands: [],
        },
      }
    }

    const primarySlug = (brand.primary_category_slug || '')
      .toString()
      .toLowerCase()
      .replace(/_/g, '-')
    const typedSlugs = ['clothing', 'shoes', 'electronics', 'furniture', 'jewelry']
    let productsEndpoint = 'catalog/products'
    if (primarySlug.startsWith('clothing')) productsEndpoint = 'catalog/clothing/products'
    else if (primarySlug.startsWith('shoes')) productsEndpoint = 'catalog/shoes/products'
    else if (primarySlug.startsWith('electronics')) productsEndpoint = 'catalog/electronics/products'
    else if (primarySlug.startsWith('furniture')) productsEndpoint = 'catalog/furniture/products'
    else if (primarySlug.startsWith('jewelry')) productsEndpoint = 'catalog/jewelry/products'

    const productParams: Record<string, any> = {
      page,
      page_size: pageSize,
      brand_id: brand.id,
    }

    if (primarySlug && !typedSlugs.some((value) => primarySlug.startsWith(value))) {
      productParams.product_type = primarySlug.replace(/-/g, '_')
    }

    const productsRes = await axios.get(getInternalApiUrl(productsEndpoint), { params: productParams })
    const productsData = productsRes.data
    const products = Array.isArray(productsData) ? productsData : productsData.results || []
    const totalCount = typeof productsData?.count === 'number' ? productsData.count : products.length

    let categories: Category[] = []
    try {
      const categoriesRes = await axios.get(getInternalApiUrl('catalog/categories?top_level=true&page_size=200'))
      const categoriesData = categoriesRes.data
      categories = Array.isArray(categoriesData) ? categoriesData : categoriesData.results || []
    } catch {
      categories = []
    }

    let brands: Brand[] = []
    try {
      const brandParams: Record<string, any> = { page_size: 200 }
      if (primarySlug) {
        brandParams.primary_category_slug = primarySlug
        brandParams.product_type = primarySlug.replace(/-/g, '_')
      }
      const brandsRes = await axios.get(getInternalApiUrl('catalog/brands'), { params: brandParams })
      const brandsData = brandsRes.data
      brands = Array.isArray(brandsData) ? brandsData : brandsData.results || []
    } catch {
      brands = []
    }

    return {
      props: {
        ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])),
        brandData: {
          name: brand.name,
          description: brand.description,
          products,
          totalCount,
        },
        page,
        categories,
        brands,
      },
    }
  } catch (e) {
    return {
      props: {
        ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])),
        brandData: null,
        page: 1,
        categories: [],
        brands: []
      }
    }
  }
}
