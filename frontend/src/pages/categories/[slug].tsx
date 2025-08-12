import { GetServerSideProps } from 'next'
import Head from 'next/head'
import axios from 'axios'
import Link from 'next/link'
import ProductCard from '../../components/ProductCard'

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
      <main className="mx-auto max-w-6xl p-6">
        <h1 className="text-2xl font-bold">{name}</h1>
        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
          {products.map((p) => (
            <ProductCard key={p.id} id={p.id} name={p.name} slug={p.slug} price={p.price} currency={p.currency} />
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
      axios.get(`${base}/api/catalog/products/`, { params: { search: '', category_id: undefined, brand_id: undefined } })
    ])
    const categories = Array.isArray(catRes.data) ? catRes.data : (catRes.data.results || [])
    const category = categories.find((c: any) => c.slug === slug)
    // Получаем товары по ID категории (бэкенд фильтрует по category_id)
    const pr = await axios.get(`${base}/api/catalog/products/`, { params: { category_id: category?.id } })
    const products = Array.isArray(pr.data) ? pr.data : (pr.data.results || [])
    return { props: { name: category?.name || 'Категория', products } }
  } catch (e) {
    return { notFound: false, props: { name: 'Категория', products: [] } }
  }
}
