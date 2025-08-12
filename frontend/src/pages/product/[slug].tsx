import { GetServerSideProps } from 'next'
import Head from 'next/head'
import axios from 'axios'
import AddToCartButton from '../../components/AddToCartButton'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'

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
  const { t } = useTranslation('common')
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
              {product.price ? `${product.price} ${product.currency}` : t('price_on_request')}
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
    return { props: { ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])), product: res.data } }
  } catch (e) {
    return { notFound: true }
  }
}
