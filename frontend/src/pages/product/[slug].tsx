import { GetServerSideProps } from 'next'
import Head from 'next/head'
import axios from 'axios'

interface Product {
  id: number
  name: string
  slug: string
  description: string
  price: string
  currency: string
  main_image: string
}

export default function ProductPage({ product }: { product: Product }) {
  if (!product) return <div>Not found</div>
  return (
    <>
      <Head>
        <title>{product.name} — Turk-Export</title>
      </Head>
      <main style={{ maxWidth: 800, margin: '0 auto', padding: 24 }}>
        <h1>{product.name}</h1>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {product.main_image ? <img src={product.main_image} alt={product.name} style={{ maxWidth: '100%', borderRadius: 8 }} /> : null}
        <div style={{ marginTop: 16, fontSize: 18, fontWeight: 600 }}>{product.price ? `${product.price} ${product.currency}` : 'Цена по запросу'}</div>
        <p style={{ marginTop: 16, whiteSpace: 'pre-wrap' }}>{product.description}</p>
      </main>
    </>
  )
}

export const getServerSideProps: GetServerSideProps = async (ctx) => {
  const { slug } = ctx.params as { slug: string }
  try {
    const base = process.env.INTERNAL_API_BASE || 'http://backend:8000'
    const res = await axios.get(`${base}/api/catalog/products/${slug}/`)
    return { props: { product: res.data } }
  } catch (e) {
    return { notFound: true }
  }
}
