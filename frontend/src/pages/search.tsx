import { useRouter } from 'next/router'
import Head from 'next/head'
import { useEffect, useState } from 'react'
import api from '../lib/api'
import { isBaseProductType } from '../lib/product'
import ProductCard from '../components/ProductCard'
import VisualSearch from '../components/VisualSearch'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useTranslation } from 'next-i18next'

export default function SearchPage() {
  const router = useRouter()
  const q = ((router.query.query || router.query.q || '') as string).trim()
  const [items, setItems] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const { t, i18n } = useTranslation('common')

  useEffect(() => {
    if (!router.isReady || !q) return
    const run = async () => {
      setLoading(true)
      try {
        // Запрашиваем товары и услуги параллельно
        const [productsRes, servicesRes] = await Promise.all([
          api.get('/catalog/products', { params: { search: q, page_size: 24 } }),
          api.get('/catalog/services', { params: { search: q, page_size: 24 } })
        ])

        const products = Array.isArray(productsRes.data) ? productsRes.data : (productsRes.data.results || [])
        // Помечаем услуги, чтобы ProductCard понимал какой тип ссылки строить
        const services = (Array.isArray(servicesRes.data) ? servicesRes.data : (servicesRes.data.results || []))
          .map((s: any) => ({ ...s, product_type: s.product_type || 'uslugi' }))

        // Объединяем результаты
        setItems([...products, ...services])
      } finally {
        setLoading(false)
      }
    }
    run()
  }, [q, router.isReady])

  return (
    <>
      <Head><title>{`${t('search_results', 'Результаты поиска')} — ${q}`}</title></Head>
      <main className="mx-auto max-w-6xl px-3 pt-0 pb-6 sm:p-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('search_results', 'Результаты поиска')}</h1>
        <div className="mt-1 text-sm text-gray-600 dark:text-gray-400">{q ? `${t('search_for', 'По запросу')}: "${q}"` : t('search_placeholder')}</div>
        <div className="mt-8">
          <VisualSearch />
        </div>
        {loading ? <div className="mt-6">Загрузка…</div> : (
          <div className="mt-6 grid grid-cols-2 gap-3 sm:gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
            {items.map((p) => {
              const pt = p.product_type || 'medicines'
              return (
                <ProductCard
                  key={p.id}
                  id={p.id}
                  baseProductId={(p as { base_product_id?: number }).base_product_id}
                  name={p.name}
                  slug={p.slug}
                  price={p.price}
                  currency={p.currency}
                  imageUrl={p.main_image_url || p.main_image}
                  videoUrl={p.main_video_url || p.video_url}
                  hasManualMainImage={(p as any).has_manual_main_image}
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
        )}
      </main>
    </>
  )
}

export async function getServerSideProps(ctx: any) {
  return { props: { ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])) } }
}
