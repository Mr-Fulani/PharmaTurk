import { GetServerSideProps } from 'next'
import Head from 'next/head'
import axios from 'axios'
import AddToCartButton from '../../components/AddToCartButton'

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
  if (!product) return <div className="mx-auto max-w-6xl p-6">Not found</div>
  return (
    <>
      <Head>
        <title>{product.name} — Turk-Export</title>
      </Head>
      <main className="mx-auto max-w-6xl p-6">
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <div>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            {product.main_image ? (
              <img src={product.main_image} alt={product.name} className="w-full rounded-xl object-cover" />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img src="/product-placeholder.svg" alt="No image" className="aspect-square w-full rounded-xl object-cover" />
            )}
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{product.name}</h1>
            <div className="mt-3 text-xl font-semibold text-gray-900">
              {product.price ? `${product.price} ${product.currency}` : 'Цена по запросу'}
            </div>
            <AddToCartButton productId={product.id} className="mt-4" />
            <div className="prose mt-6 max-w-none">
              <p className="whitespace-pre-wrap text-gray-700">{product.description}</p>
            </div>
          </div>
        </div>
      </main>
    </>
  )
}

export const getServerSideProps: GetServerSideProps = async (ctx) => {
  const { slug } = ctx.params as { slug: string }
  try {
    const base = process.env.INTERNAL_API_BASE || 'http://backend:8000'
    const res = await axios.get(`${base}/api/catalog/products/${slug}`)
    return { props: { product: res.data } }
  } catch (e) {
    return { notFound: true }
  }
}
