import Head from 'next/head'
import Link from 'next/link'
import axios from 'axios'
import AddToCartButton from '../components/AddToCartButton'
import Section from '../components/Section'
import ProductCard from '../components/ProductCard'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'

interface Product {
  id: number
  name: string
  slug: string
  price: string | null
  currency: string
  main_image_url?: string | null
}

export default function Home({ products }: { products: Product[] }) {
  return (
    <>
      <Head>
        <title>Turk-Export</title>
      </Head>
      <main>
        <Section title="Товары дня">
          <div className="no-scrollbar mt-2 grid grid-flow-col gap-4 overflow-x-auto px-1 [grid-auto-columns:minmax(240px,1fr)]">
            {products.slice(0, 8).map((p) => (
              <ProductCard key={p.id} id={p.id} name={p.name} slug={p.slug} price={p.price} currency={p.currency} imageUrl={p.main_image_url} />
            ))}
          </div>
        </Section>
        <Section title="Хиты продаж">
          <div className="no-scrollbar mt-2 grid grid-flow-col gap-4 overflow-x-auto px-1 [grid-auto-columns:minmax(240px,1fr)]">
            {products.slice(8, 16).map((p) => (
              <ProductCard key={p.id} id={p.id} name={p.name} slug={p.slug} price={p.price} currency={p.currency} imageUrl={p.main_image_url} />
            ))}
          </div>
        </Section>
      </main>
    </>
  )
}

export async function getServerSideProps(ctx: any) {
  try {
    const base = process.env.INTERNAL_API_BASE || 'http://backend:8000'
    const res = await axios.get(`${base}/api/catalog/products`)
    const data = res.data
    const products: Product[] = Array.isArray(data) ? data : (data.results || [])
    return { props: { ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])), products } }
  } catch (e) {
    return { props: { ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])), products: [] } }
  }
}
