import Head from 'next/head'
import axios from 'axios'
import Link from 'next/link'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'

interface Category {
  id: number
  name: string
  slug: string
  description?: string
  products_count?: number
}

export default function CategoriesPage({ categories }: { categories: Category[] }) {
  const { t } = useTranslation('common')
  return (
    <>
      <Head>
        <title>{t('menu_categories', 'Категории')} — Turk-Export</title>
      </Head>
      <main style={{ maxWidth: 960, margin: '0 auto', padding: 24 }}>
        <h1>{t('menu_categories', 'Категории')}</h1>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 16 }}>
          {categories.map((c) => (
            <Link key={c.id} href={`/categories/${c.slug}`} style={{
              border: '1px solid #eee', borderRadius: 8, padding: 12,
              textDecoration: 'none', color: '#111'
            }}>
              <div style={{ fontWeight: 600 }}>{c.name}</div>
              <div style={{ color: '#666', fontSize: 13, marginTop: 6 }}>
                {c.products_count ? `${c.products_count}` : ''}
              </div>
              {c.description ? (
                <p style={{ color: '#444', fontSize: 14, marginTop: 8 }}>{c.description}</p>
              ) : null}
            </Link>
          ))}
        </div>
      </main>
    </>
  )
}

export async function getServerSideProps(ctx: any) {
  try {
    const base = process.env.INTERNAL_API_BASE || 'http://backend:8000'
    const res = await axios.get(`${base}/api/catalog/categories`)
    const data = res.data
    const categories: Category[] = Array.isArray(data) ? data : (data.results || [])
    return { props: { ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])), categories } }
  } catch (e) {
    return { props: { ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])), categories: [] } }
  }
}
