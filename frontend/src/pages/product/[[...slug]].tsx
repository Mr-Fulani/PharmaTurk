import { GetServerSideProps } from 'next'
import Head from 'next/head'
import axios from 'axios'
import AddToCartButton from '../../components/AddToCartButton'
import FavoriteButton from '../../components/FavoriteButton'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'

type CategoryType =
  | 'medicines'
  | 'clothing'
  | 'shoes'
  | 'electronics'
  | 'supplements'
  | 'tableware'
  | 'furniture'
  | 'medical-equipment'

const CATEGORY_ALIASES: Record<string, CategoryType> = {
  supplements: 'medicines',
  tableware: 'tableware',
  furniture: 'furniture',
  'medical-equipment': 'medical-equipment',
}

const normalizeCategoryType = (value?: string): CategoryType => {
  if (!value) return 'medicines'
  const lower = value.toLowerCase()
  if (['medicines', 'clothing', 'shoes', 'electronics'].includes(lower)) {
    return lower as CategoryType
  }
  return CATEGORY_ALIASES[lower] || 'medicines'
}

const resolveDetailEndpoint = (type: CategoryType, slug: string) => {
  switch (type) {
    case 'clothing':
      return `/api/catalog/clothing/products/${slug}`
    case 'shoes':
      return `/api/catalog/shoes/products/${slug}`
    case 'electronics':
      return `/api/catalog/electronics/products/${slug}`
    case 'medicines':
    case 'supplements':
    case 'tableware':
    case 'furniture':
    case 'medical-equipment':
    default:
      return `/api/catalog/products/${slug}`
  }
}

interface Product {
  id: number
  name: string
  slug: string
  description: string
  price: string
  currency: string
  main_image?: string
  main_image_url?: string
}

export default function ProductPage({
  product,
  productType,
  isBaseProduct
}: {
  product: Product | null
  productType: CategoryType
  isBaseProduct: boolean
}) {
  const { t } = useTranslation('common')
  if (!product) {
    return <div className="mx-auto max-w-6xl p-6">{t('not_found', 'Товар не найден')}</div>
  }
  const image = product.main_image_url || product.main_image
  return (
    <>
      <Head>
        <title>{product.name} — Turk-Export</title>
      </Head>
      <main className="mx-auto max-w-6xl p-6">
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <div>
            {image ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={image} alt={product.name} className="w-full rounded-xl object-cover" />
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
            <div className="mt-4 flex items-center gap-3">
              <AddToCartButton
                productId={isBaseProduct ? product.id : undefined}
                productType={productType}
                productSlug={product.slug}
              />
              {product.id && (
                <FavoriteButton productId={product.id} productType={productType} iconOnly={false} />
              )}
            </div>
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
  const slugParts = (ctx.params?.slug as string[]) || []
  if (slugParts.length === 0) {
    return { notFound: true }
  }

  let categoryType: CategoryType = 'medicines'
  let productSlug: string

  if (slugParts.length === 1) {
    productSlug = slugParts[0]
  } else {
    categoryType = normalizeCategoryType(slugParts[0])
    productSlug = slugParts[1]
  }

  const base = process.env.INTERNAL_API_BASE || 'http://backend:8000'
  const endpoint = resolveDetailEndpoint(categoryType, productSlug)
  try {
    const res = await axios.get(`${base}${endpoint}`)
    const baseProductTypes: CategoryType[] = ['medicines', 'supplements', 'medical-equipment']
    const isBaseProduct = baseProductTypes.includes(categoryType)
    return {
      props: {
        ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])),
        product: res.data,
        productType: categoryType,
        isBaseProduct,
      },
    }
  } catch (error) {
    if (slugParts.length === 1) {
      return {
        redirect: {
          destination: `/product/${categoryType}/${productSlug}`,
          permanent: false,
        },
      }
    }
    return { notFound: true }
  }
}

