import { useRouter } from 'next/router'
import Head from 'next/head'
import { useEffect, useState } from 'react'
import { getSingleFlight } from '../lib/api'
import { buildProductIdentityKey, isBaseProductType } from '../lib/product'
import ProductCard from '../components/ProductCard'
import VisualSearch from '../components/VisualSearch'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useTranslation } from 'next-i18next'

export default function SearchPage() {
  const router = useRouter()
  const q = ((router.query.query || router.query.q || '') as string).trim()
  const [items, setItems] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { t, i18n } = useTranslation('common')

  useEffect(() => {
    if (!router.isReady) return
    if (!q) {
      setItems([])
      setError(null)
      setLoading(false)
      return
    }
    let cancelled = false
    const run = async () => {
      setLoading(true)
      setError(null)
      try {
        // A failure in one catalog must not hide valid results from the other.
        const [productsResult, servicesResult] = await Promise.allSettled([
          getSingleFlight('/catalog/products', { params: { search: q, page_size: 24, view: 'card', include_facets: false } }),
          getSingleFlight('/catalog/services', { params: { search: q, page_size: 24, view: 'card' } })
        ])

        if (cancelled) return

        const productsRes = productsResult.status === 'fulfilled' ? productsResult.value : null
        const servicesRes = servicesResult.status === 'fulfilled' ? servicesResult.value : null
        const products = productsRes
          ? (Array.isArray(productsRes.data) ? productsRes.data : (productsRes.data.results || []))
          : []
        // Помечаем услуги, чтобы ProductCard понимал какой тип ссылки строить
        const services = (servicesRes
          ? (Array.isArray(servicesRes.data) ? servicesRes.data : (servicesRes.data.results || []))
          : [])
          .map((s: any) => ({ ...s, product_type: s.product_type || 'uslugi' }))

        setItems([...products, ...services])
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

  return (
    <>
      <Head>
        <title>{`${t('search_results', 'Результаты поиска')} — ${q}`}</title>
        <meta name="robots" content="noindex, follow" />
      </Head>
      <main className="mx-auto max-w-6xl px-3 pt-0 pb-6 sm:p-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('search_results', 'Результаты поиска')}</h1>
        <div className="mt-1 text-sm text-gray-600 dark:text-gray-400">{q ? `${t('search_for', 'По запросу')}: "${q}"` : t('search_placeholder')}</div>
        <div className="mt-8">
          <VisualSearch />
        </div>
        <section id="search-results" className="scroll-mt-24">
          {error ? <div className="mt-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100">{error}</div> : null}
          {loading ? <div className="mt-6">{t('search_loading', 'Загрузка…')}</div> : items.length === 0 ? (
            <div className="mt-6 text-gray-600 dark:text-gray-400">{t('products_not_found', 'Товары не найдены')}</div>
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
                    rating={p.rating}
                    reviewsCount={p.reviews_count}
                    translations={p.translations}
                    locale={i18n.language}
                  />
                )
              })}
            </div>
          )}
        </section>
      </main>
    </>
  )
}

export async function getServerSideProps(ctx: any) {
  return { props: { ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])) } }
}
