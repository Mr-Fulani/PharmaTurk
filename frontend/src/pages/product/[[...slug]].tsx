import { GetServerSideProps } from 'next'
import Head from 'next/head'
import axios from 'axios'
import { useState } from 'react'
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
  | 'medical-equipment'
  | 'furniture'
  | 'tableware'
  | 'accessories'
  | 'jewelry'

const CATEGORY_ALIASES: Record<string, CategoryType> = {
  supplements: 'supplements',
  'medical-equipment': 'medical-equipment',
  medical_equipment: 'medical-equipment',
  furniture: 'furniture',
  tableware: 'tableware',
  accessories: 'accessories',
  jewelry: 'jewelry',
}

const normalizeCategoryType = (value?: string): CategoryType => {
  if (!value) return 'medicines'
  const lower = value.toLowerCase()
  if ([
    'medicines', 'clothing', 'shoes', 'electronics',
    'supplements', 'medical-equipment',
    'furniture', 'tableware', 'accessories', 'jewelry'
  ].includes(lower)) {
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
    case 'furniture':
    case 'tableware':
    case 'accessories':
    case 'jewelry':
    case 'medicines':
    case 'supplements':
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
  images?: { id: number; image_url: string; alt_text?: string; is_main?: boolean }[]
  variants?: Variant[]
  default_variant_slug?: string | null
  active_variant_slug?: string | null
  active_variant_price?: string | null
  active_variant_currency?: string | null
  active_variant_stock_quantity?: number | null
  active_variant_main_image_url?: string | null
}

interface Variant {
  id: number
  slug: string
  name?: string
  color?: string
  price?: number | string | null
  old_price?: number | string | null
  currency?: string
  is_available?: boolean
  stock_quantity?: number | null
  main_image?: string
  images?: { id: number; image_url: string; alt_text?: string; is_main?: boolean }[]
  sizes?: { id: number; size?: string; is_available?: boolean; stock_quantity?: number | null }[]
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
  const variants = product.variants || []

  // Выбираем дефолтный вариант-цвет: активный, либо первый доступный
  const initialVariant =
    variants.find((v) => v.slug === product.active_variant_slug) ||
    variants.find((v) => v.slug === product.default_variant_slug) ||
    variants.find((v) => v.is_available) ||
    variants[0] ||
    null

  const [selectedVariantSlug, setSelectedVariantSlug] = useState<string | null>(initialVariant?.slug || null)
  const selectedVariant = variants.find((v) => v.slug === selectedVariantSlug) || initialVariant

  // Цвет и размер исходя из выбранного варианта
  const [selectedColor, setSelectedColor] = useState<string | undefined>(selectedVariant?.color)
  // По умолчанию размер не выбран — пользователь должен выбрать вручную
  const [selectedSize, setSelectedSize] = useState<string | undefined>(undefined)

  // Список цветов
  const colors = Array.from(new Set((variants.map((v) => v.color).filter(Boolean) as string[])))

  // Список размеров для выбранного цвета (берем из выбранного варианта-цвета)
  const sizesForColor = selectedVariant?.sizes || []

  // Подбор варианта при смене цвета
  const pickVariant = (color?: string) => {
    const found = variants.find((v) => v.color === color) || variants[0]
    if (found) {
      setSelectedVariantSlug(found.slug)
      setSelectedColor(found.color)
      // Сброс выбора размера — пользователь должен выбрать вручную
      setSelectedSize(undefined)
      const gallerySourceLocal = found.images?.length ? found.images : product.images || []
      setActiveImage(
        found.main_image ||
          found.images?.find((img) => img.is_main)?.image_url ||
          found.images?.[0]?.image_url ||
          product.active_variant_main_image_url ||
          product.main_image_url ||
          product.main_image ||
          gallerySourceLocal.find((img) => img.is_main)?.image_url ||
          gallerySourceLocal[0]?.image_url ||
          null
      )
    }
  }

  const gallerySource = selectedVariant?.images?.length ? selectedVariant.images : (product.images || [])
  const initialImage =
    selectedVariant?.main_image ||
    selectedVariant?.images?.find((img) => img.is_main)?.image_url ||
    selectedVariant?.images?.[0]?.image_url ||
    product.active_variant_main_image_url ||
    product.main_image_url ||
    product.main_image ||
    gallerySource.find((img) => img.is_main)?.image_url ||
    gallerySource[0]?.image_url
  const [activeImage, setActiveImage] = useState<string | null>(initialImage || null)

  const displayPrice = selectedVariant?.price
    ? `${selectedVariant.price} ${selectedVariant.currency || product.currency}`
    : product.active_variant_price || (product.price ? `${product.price} ${product.currency}` : t('price_on_request'))
  const sizeRequired = sizesForColor.length > 0
  return (
    <>
      <Head>
        <title>{product.name} — Turk-Export</title>
      </Head>
      <main className="mx-auto max-w-6xl p-6">
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <div>
            {activeImage ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={activeImage} alt={product.name} className="w-full rounded-xl object-cover" />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img src="/product-placeholder.svg" alt="No image" className="aspect-square w-full rounded-xl object-cover" />
            )}
            {gallerySource.length > 1 && (
              <div className="mt-3 flex gap-2 overflow-x-auto">
                {gallerySource.map((img) => (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    key={img.id}
                    src={img.image_url}
                    alt={img.alt_text || product.name}
                    className={`h-20 w-20 rounded-lg object-cover cursor-pointer border ${activeImage === img.image_url ? 'border-violet-500 ring-2 ring-violet-300' : 'border-gray-200'}`}
                    onClick={() => setActiveImage(img.image_url)}
                  />
                ))}
              </div>
            )}
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{product.name}</h1>
            <div className="mt-3 text-xl font-semibold text-gray-900">
              {displayPrice || t('price_on_request')}
            </div>
            {(colors.length > 0 || sizesForColor.length > 0) && (
              <div className="mt-4 flex flex-col gap-4">
                {colors.length > 0 && (
                  <div className="flex flex-col gap-2">
                    <span className="text-sm text-gray-700">{t('color', 'Цвет')}</span>
                    <div className="flex flex-wrap gap-2">
                      {colors.map((c) => {
                        const isActive = c === selectedColor
                        return (
                          <button
                            key={c}
                            onClick={() => {
                              setSelectedColor(c)
                              pickVariant(c)
                            }}
                            className={`rounded-md px-3 py-1 text-sm border transition ${
                              isActive
                                ? 'border-violet-600 bg-violet-50 text-violet-700'
                                : 'border-gray-300 bg-white text-gray-800 hover:border-violet-400'
                            }`}
                          >
                            {c}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}
                {sizesForColor.length > 0 && (
                  <div className="flex flex-col gap-2">
                    <span className="text-sm text-gray-700">{t('size', 'Размер')}</span>
                    <div className="flex flex-wrap gap-2">
                      {sizesForColor.map((s) => {
                        const sizeValue = s.size || ''
                        const isAvailable = s.is_available !== false && (s.stock_quantity === null || s.stock_quantity === undefined || s.stock_quantity > 0)
                        const isActive = sizeValue === selectedSize
                        return (
                          <button
                            key={sizeValue}
                            onClick={() => {
                              if (!isAvailable) return
                              setSelectedSize(sizeValue)
                            }}
                            className={`min-w-[56px] rounded-md px-3 py-2 text-sm border transition ${
                              isAvailable
                                ? isActive
                                  ? 'border-violet-600 bg-violet-50 text-violet-700'
                                  : 'border-gray-300 bg-white text-gray-800 hover:border-violet-400'
                                : 'border-gray-200 bg-gray-100 text-gray-400 cursor-not-allowed'
                            }`}
                            disabled={!isAvailable}
                          >
                            {sizeValue || t('size', 'Размер')}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}
            <div className="mt-4 flex items-center gap-3">
            <AddToCartButton
              productId={isBaseProduct ? product.id : undefined}
              productType={productType}
              productSlug={!isBaseProduct ? (selectedVariantSlug || product.slug) : product.slug}
              size={selectedSize}
              requireSize={!isBaseProduct && sizeRequired}
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
    const baseProductTypes: CategoryType[] = [
      'medicines', 'supplements', 'medical-equipment',
      'furniture', 'tableware', 'accessories', 'jewelry'
    ]
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

