import { useRouter } from 'next/router'
import Head from 'next/head'
import Link from 'next/link'
import { useEffect, useMemo, useRef, useState } from 'react'
import { getSingleFlight } from '../lib/api'
import {
  appendSearchPage,
  hasSearchFilters,
  nextSearchSource,
  readSearchFacets,
  readSearchFilters,
  readSearchInfo,
  readSearchPage,
  searchPageQuery,
  searchProductParams,
  searchServiceParams,
} from '../lib/searchResults'
import SearchFilters, { type SearchFiltersValue } from '../components/SearchFilters'
import { buildProductIdentityKey, isBaseProductType } from '../lib/product'
import ProductCard from '../components/ProductCard'
import VisualSearch from '../components/VisualSearch'
import dynamic from 'next/dynamic'

const SourcingRequestForm = dynamic(() => import('../components/SourcingRequestForm'), { ssr: false })
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useTranslation } from 'next-i18next'
import { gtmSearch } from '../lib/gtm'

type SourceState = { items: any[]; count: number; page: number; hasMore: boolean }
const EMPTY_SOURCE: SourceState = { items: [], count: 0, page: 1, hasMore: false }

// Помечаем услуги, чтобы ProductCard понимал какой тип ссылки строить
function markServices(results: any[]) {
  return results.map((s: any) => ({ ...s, product_type: s.product_type || 'uslugi' }))
}

export default function SearchPage() {
  const router = useRouter()
  const q = ((router.query.query || router.query.q || '') as string).trim()
  const [products, setProducts] = useState<SourceState>(EMPTY_SOURCE)
  const [services, setServices] = useState<SourceState>(EMPTY_SOURCE)
  const [loadingMore, setLoadingMore] = useState(false)
  const [moreError, setMoreError] = useState<string | null>(null)
  // Нашлось не по запросу как есть: другая раскладка, латиница или опечатка (search_info API)
  const [searchInfo, setSearchInfo] = useState<{ mode: string; query: string } | null>(null)
  // Запрос, к которому относятся показанные результаты: ответ «Показать ещё»
  // по прежнему запросу не должен попасть в список нового.
  // Фильтры и сортировка живут в адресе (?type=&brand=&available=&sort=): ссылкой можно поделиться.
  const { type: filterType, brand: filterBrand, available: filterAvailable, sort: filterSort } = readSearchFilters(router.query)
  const filters: SearchFiltersValue = useMemo(
    () => ({ type: filterType, brand: filterBrand, available: filterAvailable, sort: filterSort }),
    [filterType, filterBrand, filterAvailable, filterSort],
  )
  // Услуги не делятся на разделы и бренды и не сортируются по цене вместе с товарами.
  const withServices = !hasSearchFilters(filters) && filters.sort === 'relevance'
  const [facets, setFacets] = useState<ReturnType<typeof readSearchFacets>>({ types: [], brands: [] })
  const requestKey = `${q}|${filterType}|${filterBrand}|${filterAvailable}|${filterSort}`
  const queryRef = useRef(requestKey)
  queryRef.current = requestKey
  // С запросом в URL страница сразу (и в SSR) в состоянии загрузки: иначе первым
  // кадром мелькает «Товары не найдены».
  const [loading, setLoading] = useState(Boolean(q))
  const [error, setError] = useState<string | null>(null)
  const { t, i18n } = useTranslation('common')

  useEffect(() => {
    if (!router.isReady) return
    setMoreError(null)
    setLoadingMore(false)
    setSearchInfo(null)
    if (!q) {
      setProducts(EMPTY_SOURCE)
      setServices(EMPTY_SOURCE)
      setFacets({ types: [], brands: [] })
      setError(null)
      setLoading(false)
      return
    }
    if (!hasSearchFilters(filters) && filters.sort === 'relevance') gtmSearch(q)
    let cancelled = false
    const run = async () => {
      setLoading(true)
      setError(null)
      try {
        // A failure in one catalog must not hide valid results from the other.
        const [productsResult, servicesResult] = await Promise.allSettled([
          getSingleFlight('/catalog/products', { params: searchProductParams(q, 1, filters) }),
          withServices
            ? getSingleFlight('/catalog/services', { params: searchServiceParams(q) })
            : Promise.resolve({ data: { count: 0, next: null, results: [] } }),
        ])

        if (cancelled) return

        const productsRes = productsResult.status === 'fulfilled' ? productsResult.value : null
        const servicesRes = servicesResult.status === 'fulfilled' ? servicesResult.value : null
        const productPage = readSearchPage(productsRes?.data)
        const servicePage = readSearchPage(servicesRes?.data)

        setProducts({ items: productPage.results, count: productPage.count, page: 1, hasMore: productPage.hasMore })
        setSearchInfo(readSearchInfo(productsRes?.data))
        if (productsRes) setFacets(readSearchFacets(productsRes.data))
        setServices({ items: markServices(servicePage.results), count: servicePage.count, page: 1, hasMore: servicePage.hasMore })
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
  }, [q, filters, withServices, router.isReady, t])

  const source = nextSearchSource(products, services)

  const loadMore = async () => {
    if (!source) return
    const requestQuery = q
    const requestedKey = requestKey
    const current = source === 'products' ? products : services
    const nextPage = current.page + 1
    setLoadingMore(true)
    try {
      const res = source === 'products'
        ? await getSingleFlight('/catalog/products', { params: searchProductParams(requestQuery, nextPage, filters) })
        : await getSingleFlight('/catalog/services', { params: searchServiceParams(requestQuery, nextPage) })
      if (queryRef.current !== requestedKey) return
      const page = readSearchPage(res.data)
      const update = (state: SourceState): SourceState => ({
        items: appendSearchPage(state.items, source === 'services' ? markServices(page.results) : page.results),
        count: page.count,
        page: nextPage,
        hasMore: page.hasMore,
      })
      if (source === 'products') setProducts(update)
      else setServices(update)
      setMoreError(null)
    } catch {
      if (queryRef.current === requestedKey) {
        setMoreError(t('search_partial_error', 'Часть результатов временно недоступна.'))
      }
    } finally {
      if (queryRef.current === requestedKey) setLoadingMore(false)
    }
  }

  const items = [...products.items, ...services.items]
  const total = products.count + services.count
  const filtered = hasSearchFilters(filters)
  const applyFilters = (next: SearchFiltersValue) => {
    void router.replace({ pathname: '/search', query: searchPageQuery(q, next) }, undefined, { shallow: true, scroll: false })
  }

  return (
    <>
      <Head>
        <title>{`${t('search_results', 'Результаты поиска')} — ${q}`}</title>
        <meta name="robots" content="noindex, follow" />
      </Head>
      <main className="mx-auto max-w-page px-3 pt-0 pb-6 sm:p-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('search_results', 'Результаты поиска')}</h1>
        <div className="mt-1 text-sm text-gray-600 dark:text-gray-400">{q ? `${t('search_for', 'По запросу')}: "${q}"` : t('search_placeholder')}</div>
        {q && !loading && searchInfo && products.count > 0 ? (
          <div className="mt-1 text-sm text-gray-600 dark:text-gray-400">
            {searchInfo.mode === 'typo'
              ? t('search_did_you_mean', 'Точных совпадений нет. Возможно, вы искали')
              : searchInfo.mode === 'partial'
                ? t('search_partial', 'По запросу целиком ничего не нашлось. Показаны результаты по запросу')
                : t('search_shown_for', 'Показаны результаты по запросу')}{' '}
            <Link href={{ pathname: '/search', query: { query: searchInfo.query } }} className="font-medium text-[var(--accent)] underline">
              «{searchInfo.query}»
            </Link>
          </div>
        ) : null}
        {q && !loading && total > 0 ? (
          <div className="mt-1 text-sm text-gray-600 dark:text-gray-400">{t('search_found_count', 'Найдено: {{count}}', { count: total })}</div>
        ) : null}
        <div className="mt-8">
          <VisualSearch />
        </div>
        {/* С запросом блок не ниже экрана: пока идёт поиск и когда ничего не нашлось,
            подвал остаётся за краем экрана и не прыгает (CLS) */}
        <section id="search-results" className={`scroll-mt-24${q ? ' min-h-screen' : ''}`}>
          {q && (facets.types.length > 0 || filtered) ? <SearchFilters facets={facets} value={filters} onChange={applyFilters} /> : null}
          {error ? <div className="mt-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100">{error}</div> : null}
          {loading ? <div className="mt-6">{t('search_loading', 'Загрузка…')}</div> : items.length === 0 ? (
            <div className="mt-6">
              <div className="text-gray-600 dark:text-gray-400">
                {filtered ? t('search_filters_empty', 'С такими фильтрами ничего не нашлось.') : t('products_not_found', 'Товары не найдены')}
              </div>
              {filtered ? (
                <button
                  type="button"
                  onClick={() => applyFilters({ type: '', brand: null, available: false, sort: filters.sort })}
                  className="mt-4 min-h-[44px] rounded-lg border border-[var(--border)] px-6 py-2 text-sm font-medium text-[var(--text-strong)] hover:border-[var(--accent)]"
                >
                  {t('search_filters_reset', 'Сбросить фильтры')}
                </button>
              ) : q ? (
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
                    isHospital={Boolean((p as { is_hospital?: boolean }).is_hospital)}
                    rating={p.rating}
                    reviewsCount={p.reviews_count}
                    translations={p.translations}
                    locale={i18n.language}
                  />
                )
              })}
            </div>
          )}
          {moreError ? <div className="mt-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100">{moreError}</div> : null}
          {!loading && source ? (
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
