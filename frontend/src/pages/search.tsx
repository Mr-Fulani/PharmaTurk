import { useRouter } from 'next/router'
import Head from 'next/head'
import { useEffect, useState } from 'react'
import { getSingleFlight } from '../lib/api'
import { appendSearchPage, readSearchPage, searchProductParams } from '../lib/searchResults'
import { buildProductIdentityKey, isBaseProductType } from '../lib/product'
import ProductCard from '../components/ProductCard'
import VisualSearch from '../components/VisualSearch'
import dynamic from 'next/dynamic'

const SourcingRequestForm = dynamic(() => import('../components/SourcingRequestForm'), { ssr: false })
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useTranslation } from 'next-i18next'
import { gtmSearch } from '../lib/gtm'

export default function SearchPage() {
  const router = useRouter()
  const q = ((router.query.query || router.query.q || '') as string).trim()
  const [products, setProducts] = useState<any[]>([])
  const [services, setServices] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  // С запросом в URL страница сразу (и в SSR) в состоянии загрузки: иначе первым
  // кадром мелькает «Товары не найдены».
  const [loading, setLoading] = useState(Boolean(q))
  const [error, setError] = useState<string | null>(null)
  const { t, i18n } = useTranslation('common')

  useEffect(() => {
    if (!router.isReady) return
    if (!q) {
      setProducts([])
      setServices([])
      setTotal(0)
      setHasMore(false)
      setError(null)
      setLoading(false)
      return
    }
    gtmSearch(q)
    let cancelled = false
    const run = async () => {
      setLoading(true)
      setError(null)
      try {
        // A failure in one catalog must not hide valid results from the other.
        const [productsResult, servicesResult] = await Promise.allSettled([
          getSingleFlight('/catalog/products', { params: searchProductParams(q) }),
          getSingleFlight('/catalog/services', { params: { search: q, page_size: 24, view: 'card' } })
        ])

        if (cancelled) return

        const productsRes = productsResult.status === 'fulfilled' ? productsResult.value : null
        const servicesRes = servicesResult.status === 'fulfilled' ? servicesResult.value : null
        const productPage = readSearchPage(productsRes?.data)
        const servicePage = readSearchPage(servicesRes?.data)
        // Помечаем услуги, чтобы ProductCard понимал какой тип ссылки строить
        const foundServices = servicePage.results.map((s: any) => ({ ...s, product_type: s.product_type || 'uslugi' }))

        setProducts(productPage.results)
        setServices(foundServices)
        setTotal(productPage.count + foundServices.length)
        setPage(1)
        setHasMore(productPage.hasMore)
        if (!productsRes && !servicesRes) {
          setError(t('search_error', 'Не удалось выполнить поиск. Попробуйте ещё раз.'))
        } else if (!productsRes || !servicesRes) {
          setError(t('search_partial_error', 'Часть результатов временно недоступна.'))
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void run()
    return () => {
      cancelled = true
    }
  }, [q, router.isReady, t])

  const loadMore = async () => {
    const nextPage = page + 1
    setLoadingMore(true)
    try {
      const res = await getSingleFlight('/catalog/products', { params: searchProductParams(q, nextPage) })
      const productPage = readSearchPage(res.data)
      setProducts((current) => appendSearchPage(current, productPage.results))
      setPage(nextPage)
      setHasMore(productPage.hasMore)
    } catch {
      setError(t('search_partial_error', 'Часть результатов временно недоступна.'))
    } finally {
      setLoadingMore(false)
    }
  }

  const items = [...products, ...services]

  return (
    <>
      <Head>
        <title>{`${t('search_results', 'Результаты поиска')} — ${q}`}</title>
        <meta name="robots" content="noindex, follow" />
      </Head>
      <main className="mx-auto max-w-6xl px-3 pt-0 pb-6 sm:p-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('search_results', 'Результаты поиска')}</h1>
        <div className="mt-1 text-sm text-gray-600 dark:text-gray-400">{q ? `${t('search_for', 'По запросу')}: "${q}"` : t('search_placeholder')}</div>
        {q && !loading && total > 0 ? (
          <div className="mt-1 text-sm text-gray-600 dark:text-gray-400">{t('search_found_count', 'Найдено: {{count}}', { count: total })}</div>
        ) : null}
        <div className="mt-8">
          <VisualSearch />
        </div>
        {/* С запросом блок не ниже экрана: пока идёт поиск и когда ничего не нашлось,
            подвал остаётся за краем экрана и не прыгает (CLS) */}
        <section id="search-results" className={`scroll-mt-24${q ? ' min-h-screen' : ''}`}>
          {error ? <div className="mt-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100">{error}</div> : null}
          {loading ? <div className="mt-6">{t('search_loading', 'Загрузка…')}</div> : items.length === 0 ? (
            <div className="mt-6">
              <div className="text-gray-600 dark:text-gray-400">{t('products_not_found', 'Товары не найдены')}</div>
              {q ? (
                <div className="mt-6">
                  <SourcingRequestForm placement="search" initialComment={q} />
                </div>
              ) : null}
            </div>
          ) : (
            <div className="mt-6 grid grid-cols-2 gap-3 sm:gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
              {items.map((p) => {
                const pt = p.product_type || 'medicines'
                return (
                  <ProductCard
                    key={buildProductIdentityKey(p, pt)}
                    id={p.id}
                    baseProductId={(p as { base_product_id?: number }).base_product_id}
                    name={p.name}
                    slug={p.slug}
                    price={p.price}
                    currency={p.currency}
                    imageUrl={p.main_image_url || p.main_image}
                    galleryImages={p.images}
                    videoUrl={p.video_url}
                    mainVideoUrl={p.main_video_url}
                    mainGifUrl={p.main_gif_url}
                    hasManualMainImage={(p as any).has_manual_main_image}
                    productType={pt}
                    isBaseProduct={isBaseProductType(pt)}
                    isNew={(p as { is_new?: boolean }).is_new}
                    isFeatured={(p as { is_featured?: boolean }).is_featured}
                    importRestrictedCountries={(p as { import_restricted_countries?: string[] }).import_restricted_countries}
                    rating={p.rating}
                    reviewsCount={p.reviews_count}
                    translations={p.translations}
                    locale={i18n.language}
                  />
                )
              })}
            </div>
          )}
          {!loading && hasMore ? (
            <div className="mt-6 flex justify-center">
              <button
                type="button"
                onClick={() => void loadMore()}
                disabled={loadingMore}
                className="min-h-[44px] rounded-lg border border-gray-300 px-6 py-2 text-sm font-medium text-gray-900 hover:bg-gray-50 disabled:opacity-60 dark:border-gray-700 dark:text-white dark:hover:bg-gray-800"
              >
                {loadingMore ? t('search_loading', 'Загрузка…') : t('search_show_more', 'Показать ещё')}
              </button>
            </div>
          ) : null}
        </section>
      </main>
    </>
  )
}

export async function getServerSideProps(ctx: any) {
  return { props: { ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])) } }
}
