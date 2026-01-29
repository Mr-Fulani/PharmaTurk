import { GetServerSideProps } from 'next'
import Head from 'next/head'
import axios from 'axios'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import AddToCartButton from '../../components/AddToCartButton'
import BuyNowButton from '../../components/BuyNowButton'
import SecurityAndService from '../../components/SecurityAndService'
import FavoriteButton from '../../components/FavoriteButton'
import SimilarProducts from '../../components/SimilarProducts'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { getLocalizedColor, getLocalizedProductDescription, ProductTranslation } from '../../lib/i18n'
import { useTheme } from '../../context/ThemeContext'

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
  | 'underwear'
  | 'headwear'

const CATEGORY_ALIASES: Record<string, CategoryType> = {
  supplements: 'supplements',
  'medical-equipment': 'medical-equipment',
  medical_equipment: 'medical-equipment',
  furniture: 'furniture',
  tableware: 'tableware',
  accessories: 'accessories',
  jewelry: 'jewelry',
  underwear: 'underwear',
  headwear: 'headwear',
}

const normalizeCategoryType = (value?: string): CategoryType => {
  if (!value) return 'medicines'
  const lower = value.toLowerCase()
  if ([
    'medicines', 'clothing', 'shoes', 'electronics',
    'supplements', 'medical-equipment',
    'furniture', 'tableware', 'accessories', 'jewelry',
    'underwear', 'headwear'
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
  video_url?: string
  images?: { id: number; image_url: string; alt_text?: string; is_main?: boolean }[]
  variants?: Variant[]
  default_variant_slug?: string | null
  active_variant_slug?: string | null
  active_variant_price?: string | null
  active_variant_currency?: string | null
  active_variant_stock_quantity?: number | null
  active_variant_main_image_url?: string | null
  translations?: ProductTranslation[]
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
  active_variant_currency?: string | null
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
  // Количество товара
  const [quantity, setQuantity] = useState(1)
  // Состояние раскрытия описания
  const [isDescriptionExpanded, setIsDescriptionExpanded] = useState(false)

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

  const router = useRouter()
  const { theme } = useTheme()
  
  // Формируем галерею: главное изображение + дополнительные изображения
  const buildGallerySource = () => {
    const variantImages = selectedVariant?.images || []
    const productImages = product.images || []
    const mainImageUrl = selectedVariant?.main_image || product.main_image_url || product.main_image
    
    // Используем изображения варианта если есть, иначе изображения продукта
    const baseImages = variantImages.length > 0 ? variantImages : productImages
    
    // Если есть главное изображение и его нет в списке, добавляем его первым
    if (mainImageUrl && !baseImages.some(img => img.image_url === mainImageUrl)) {
      return [
        { id: 0, image_url: mainImageUrl, alt_text: product.name, is_main: true, sort_order: -1 },
        ...baseImages
      ]
    }
    
    return baseImages
  }
  
  const gallerySource = buildGallerySource()
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

  // Обновляем главную картинку при изменении товара или варианта
  useEffect(() => {
    const currentGallerySource = selectedVariant?.images?.length ? selectedVariant.images : (product.images || [])
    const newImage =
      selectedVariant?.main_image ||
      selectedVariant?.images?.find((img) => img.is_main)?.image_url ||
      selectedVariant?.images?.[0]?.image_url ||
      product.active_variant_main_image_url ||
      product.main_image_url ||
      product.main_image ||
      currentGallerySource.find((img) => img.is_main)?.image_url ||
      currentGallerySource[0]?.image_url ||
      null
    setActiveImage(newImage)
  }, [product.id, product.slug, product.main_image_url, product.main_image, product.active_variant_main_image_url, selectedVariantSlug, selectedVariant?.main_image, selectedVariant?.images, product.images, router.asPath])

  // Получаем числовое значение цены для расчетов
  const priceValue = selectedVariant?.price 
    ? parseFloat(String(selectedVariant.price))
    : (product.active_variant_price ? parseFloat(String(product.active_variant_price)) : (product.price ? parseFloat(String(product.price)) : null))
  const currency = selectedVariant?.currency || product.currency || 'USD'
  
  // Вычисляем общую сумму с учетом количества
  const totalPrice = priceValue !== null ? (priceValue * quantity).toFixed(2) : null
  const displayPrice = priceValue !== null 
    ? `${priceValue} ${currency}`
    : t('price_on_request')
  const displayTotalPrice = totalPrice !== null 
    ? `${totalPrice} ${currency}`
    : t('price_on_request')
  
  const sizeRequired = sizesForColor.length > 0
  const siteUrl = (process.env.NEXT_PUBLIC_SITE_URL || 'https://pharmaturk.ru').replace(/\/$/, '')
  const productPath = isBaseProduct ? `/product/${product.slug}` : `/product/${productType}/${product.slug}`
  const canonicalUrl = `${siteUrl}${productPath}`
  const metaTitle = `${product.name} — PharmaTurk`
  const metaDescription = product.description?.slice(0, 200) || `${product.name} — ${t('buy_on_pharmaturk', 'купить на PharmaTurk')}`
  const ogImage = activeImage || product.active_variant_main_image_url || product.main_image_url || product.main_image || '/product-placeholder.svg'
  const availability =
    selectedVariant?.is_available === false || selectedVariant?.stock_quantity === 0
      ? 'https://schema.org/OutOfStock'
      : 'https://schema.org/InStock'
  const priceForSchema = selectedVariant?.price || product.price || product.active_variant_price
  const currencyForSchema = selectedVariant?.currency || product.currency || selectedVariant?.active_variant_currency
  const productSchema = {
    '@context': 'https://schema.org',
    '@type': 'Product',
    name: product.name,
    description: metaDescription,
    image: ogImage,
    sku: product.slug,
    offers: priceForSchema
      ? {
          '@type': 'Offer',
          price: priceForSchema,
          priceCurrency: currencyForSchema || 'USD',
          availability,
          url: canonicalUrl,
        }
      : undefined,
  }
  return (
    <>
      <Head>
        <title>{metaTitle}</title>
        <meta name="description" content={metaDescription} />
        <link rel="canonical" href={canonicalUrl} />
        <link rel="alternate" hrefLang="ru" href={canonicalUrl} />
        <meta property="og:title" content={metaTitle} />
        <meta property="og:description" content={metaDescription} />
        <meta property="og:url" content={canonicalUrl} />
        <meta property="og:type" content="product" />
        <meta property="og:image" content={ogImage} />
        <meta property="twitter:card" content="summary_large_image" />
        <meta property="twitter:title" content={metaTitle} />
        <meta property="twitter:description" content={metaDescription} />
        <script
          type="application/ld+json"
          // eslint-disable-next-line react/no-danger
          dangerouslySetInnerHTML={{ __html: JSON.stringify(productSchema) }}
        />
      </Head>
      <main className="mx-auto max-w-6xl p-6">
        <div className="grid grid-cols-1 gap-6 md:grid-cols-[1.3fr_1fr] md:items-start">
          <div className="flex gap-4 md:h-[calc(100vh-22rem)] md:sticky md:top-6 md:self-start">
            {/* Миниатюры слева вертикально */}
            {gallerySource.length > 1 && (
              <div className="flex flex-col gap-3 overflow-y-auto flex-shrink-0">
                {gallerySource.map((img) => (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    key={img.id}
                    src={img.image_url}
                    alt={img.alt_text || product.name}
                    className={`w-28 h-28 rounded-lg object-cover cursor-pointer border flex-shrink-0 ${activeImage === img.image_url ? 'border-violet-500 ring-2 ring-violet-300' : 'border-gray-200 hover:border-gray-300'}`}
                    onClick={() => setActiveImage(img.image_url)}
                  />
                ))}
              </div>
            )}
            {/* Главная картинка/видео справа */}
            <div className="flex-1 h-full flex items-center justify-center rounded-xl">
              {product.video_url ? (
                <video 
                  src={product.video_url} 
                  poster={activeImage || '/product-placeholder.svg'}
                  controls
                  playsInline
                  muted
                  className="max-w-full max-h-full rounded-xl object-contain"
                />
              ) : activeImage ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={activeImage} alt={product.name} className="max-w-full max-h-full rounded-xl object-contain" />
              ) : (
                // eslint-disable-next-line @next/next/no-img-element
                <img src="/product-placeholder.svg" alt="No image" className="max-w-full max-h-full rounded-xl object-contain" />
              )}
            </div>
          </div>
          <div>
            <h1 
              className="text-2xl font-bold"
              style={{ color: theme === 'dark' ? '#ffffff' : '#111827' }}
            >
              {product.name}
            </h1>
            <div 
              className="mt-3 text-xl font-semibold"
              style={{ color: theme === 'dark' ? '#ffffff' : '#111827' }}
            >
              {displayPrice || t('price_on_request')}
            </div>
            {(colors.length > 0 || sizesForColor.length > 0) && (
              <div className="mt-4 flex flex-col gap-4">
                {colors.length > 0 && (
                  <div className="flex flex-col gap-2">
                    <span 
                      className="text-sm font-semibold"
                      style={{ color: theme === 'dark' ? '#e5e7eb' : '#111827' }}
                    >
                      {t('color', 'Цвет')}
                    </span>
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
                            {getLocalizedColor(c, t)}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}
                {sizesForColor.length > 0 && (
                  <div className="flex flex-col gap-2">
                    <span 
                      className="text-sm font-semibold"
                      style={{ color: theme === 'dark' ? '#e5e7eb' : '#111827' }}
                    >
                      {t('size', 'Размер')}
                    </span>
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
            
            {/* Селектор количества */}
            <div className="mt-4 flex flex-col gap-2">
              <span 
                className="text-sm font-semibold"
                style={{ color: theme === 'dark' ? '#e5e7eb' : '#111827' }}
              >
                {t('quantity', 'Количество')}
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setQuantity(Math.max(1, quantity - 1))}
                  disabled={quantity <= 1}
                  className="flex h-10 w-10 items-center justify-center rounded-md border border-gray-300 bg-white dark:bg-gray-800 dark:border-gray-600 text-gray-700 dark:text-gray-200 transition-colors hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
                  aria-label={t('decrease_quantity', 'Уменьшить количество')}
                >
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
                  </svg>
                </button>
                <span 
                  className="min-w-[3rem] text-center text-2xl font-extrabold"
                  style={{ color: theme === 'dark' ? '#ffffff' : '#111827' }}
                >
                  {quantity}
                </span>
                <button
                  onClick={() => setQuantity(quantity + 1)}
                  className="flex h-10 w-10 items-center justify-center rounded-md border border-gray-300 bg-white dark:bg-gray-800 dark:border-gray-600 text-gray-700 dark:text-gray-200 transition-colors hover:bg-gray-50 dark:hover:bg-gray-700"
                  aria-label={t('increase_quantity', 'Увеличить количество')}
                >
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Кнопки действий */}
            <div className="mt-4 flex flex-col gap-3">
            <AddToCartButton
              productId={isBaseProduct ? product.id : undefined}
              productType={productType}
              productSlug={!isBaseProduct ? (selectedVariantSlug || product.slug) : product.slug}
              size={selectedSize}
              requireSize={!isBaseProduct && sizeRequired}
                quantity={quantity}
                showPrice={true}
                price={displayTotalPrice}
                className="w-full"
                label={t('add_to_cart', 'В корзину')}
              />
              <BuyNowButton
                productId={isBaseProduct ? product.id : undefined}
                productType={productType}
                productSlug={!isBaseProduct ? (selectedVariantSlug || product.slug) : product.slug}
                size={selectedSize}
                requireSize={!isBaseProduct && sizeRequired}
                quantity={quantity}
                className="w-full"
            />
              {product.id && (
                <div className="flex justify-center">
                <FavoriteButton productId={product.id} productType={productType} iconOnly={false} />
                </div>
              )}
            </div>

            {/* Безопасность и сервис */}
            <SecurityAndService />
          </div>
        </div>

        {/* Описание товара - на всю ширину */}
        <div 
          className="mt-6 rounded-lg border dark:border-gray-700 overflow-hidden w-full"
          style={{ 
            borderColor: theme === 'dark' ? '#374151' : '#E5E7EB',
            backgroundColor: theme === 'dark' ? '#1F2937' : '#FFF8E7'
          }}
        >
          <button
            onClick={() => setIsDescriptionExpanded(!isDescriptionExpanded)}
            className="w-full flex items-center justify-between p-4 text-left transition-colors"
            style={{ 
              backgroundColor: 'transparent'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = theme === 'dark' ? '#374151' : '#FFF5DC'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'transparent'
            }}
          >
            <span 
              className="font-medium"
              style={{ color: theme === 'dark' ? '#ffffff' : '#111827' }}
            >
              {t('description', 'Описание')}
            </span>
            <svg
              className={`w-5 h-5 transition-transform ${isDescriptionExpanded ? 'rotate-180' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              style={{ color: theme === 'dark' ? '#D1D5DB' : '#4B5563' }}
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {isDescriptionExpanded && (
            <div 
              className="border-t dark:border-gray-700 p-6"
              style={{ 
                borderTopColor: theme === 'dark' ? '#374151' : '#E5E7EB',
                backgroundColor: theme === 'dark' ? '#111827' : '#FFFBF0'
              }}
            >
              <div className="prose max-w-none dark:prose-invert">
                <p 
                  className="whitespace-pre-wrap leading-relaxed text-base"
                  style={{ color: theme === 'dark' ? '#F3F4F6' : '#111827' }}
                >
                  {getLocalizedProductDescription(product.description, t, product.translations, router.locale)}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Похожие товары */}
        <SimilarProducts
          productType={productType}
          currentProductId={product.id}
          currentProductSlug={product.slug}
          limit={8}
        />
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
  
  // Извлекаем валюту из cookie
  const cookieHeader: string = ctx.req.headers.cookie || ''
  const currencyMatch = cookieHeader.match(/(?:^|;\s*)currency=([^;]+)/)
  const currency = currencyMatch ? currencyMatch[1] : 'RUB'
  
  try {
    const res = await axios.get(`${base}${endpoint}`, {
      headers: {
        'X-Currency': currency,
        'Accept-Language': ctx.locale || 'en'
      }
    })
    const baseProductTypes: CategoryType[] = [
      'medicines', 'supplements', 'medical-equipment',
      'furniture', 'tableware', 'accessories', 'jewelry',
      'underwear', 'headwear'
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

