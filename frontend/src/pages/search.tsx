import { useRouter } from 'next/router'
import Head from 'next/head'
import { useEffect, useState } from 'react'
import api from '../lib/api'
import ProductCard from '../components/ProductCard'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useTranslation } from 'next-i18next'

export default function SearchPage() {
  const router = useRouter()
  const q = (router.query.query as string) || ''
  const [items, setItems] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const { t } = useTranslation('common')

  useEffect(() => {
    const run = async () => {
      if (!q) return
      setLoading(true)
        try {
        const r = await api.get('/catalog/products', { params: { search: q, page_size: 24 } })
        const data = Array.isArray(r.data) ? r.data : (r.data.results || [])
        setItems(data)
      } finally {
        setLoading(false)
      }
    }
    run()
  }, [q])

  return (
    <>
      <Head><title>{t('search_results', 'Результаты поиска')} — {q}</title></Head>
      <main className="mx-auto max-w-6xl p-6">
        <h1 className="text-2xl font-bold">{t('search_results', 'Результаты поиска')}</h1>
        <div className="mt-1 text-sm text-gray-600">{q ? `${t('search_for', 'По запросу')}: "${q}"` : t('search_placeholder')}</div>
        {loading ? <div className="mt-6">Загрузка…</div> : (
          <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
            {items.map((p) => (
              <ProductCard key={p.id} id={p.id} name={p.name} slug={p.slug} price={p.price} currency={p.currency} imageUrl={p.main_image_url || p.main_image} />
            ))}
          </div>
        )}
      </main>
    </>
  )
}

export async function getServerSideProps(ctx: any) {
  return { props: { ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])) } }
}


