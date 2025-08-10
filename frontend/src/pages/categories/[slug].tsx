import { GetServerSideProps } from 'next'
import Head from 'next/head'
import axios from 'axios'
import Link from 'next/link'

interface Product {
  id: number
  name: string
  slug: string
  price: string | null
  currency: string
}

export default function CategoryPage({ name, products }: { name: string, products: Product[] }) {
  return (
    <>
      <Head>
        <title>{name} — Turk-Export</title>
      </Head>
      <main style={{ maxWidth: 960, margin: '0 auto', padding: 24 }}>
        <h1>{name}</h1>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16 }}>
          {products.map((p) => (
            <div key={p.id} style={{ border: '1px solid #eee', borderRadius: 8, padding: 12 }}>
              <h3 style={{ marginTop: 8 }}>{p.name}</h3>
              <div style={{ fontWeight: 600 }}>{p.price ? `${p.price} ${p.currency}` : 'Цена по запросу'}</div>
              <Link href={`/product/${p.slug}`} style={{ display: 'inline-block', marginTop: 8 }}>Подробнее</Link>
            </div>
          ))}
        </div>
      </main>
    </>
  )
}

export const getServerSideProps: GetServerSideProps = async (ctx) => {
  const { slug } = ctx.params as { slug: string }
  const base = process.env.INTERNAL_API_BASE || 'http://backend:8000'
  try {
    const [catRes, prodRes] = await Promise.all([
      axios.get(`${base}/api/catalog/categories/`),
      axios.get(`${base}/api/catalog/products/?category_slug=${slug}`)
    ])
    const categories = Array.isArray(catRes.data) ? catRes.data : (catRes.data.results || [])
    const category = categories.find((c: any) => c.slug === slug)
    const products = Array.isArray(prodRes.data) ? prodRes.data : (prodRes.data.results || [])
    return { props: { name: category?.name || 'Категория', products } }
  } catch (e) {
    return { notFound: false, props: { name: 'Категория', products: [] } }
  }
}
