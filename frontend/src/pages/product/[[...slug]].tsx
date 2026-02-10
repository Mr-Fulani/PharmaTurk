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
import { getLocalizedColor, getLocalizedCoverType, getLocalizedProductDescription, ProductTranslation } from '../../lib/i18n'
import { resolveMediaUrl, isVideoUrl } from '../../lib/media'
import { useTheme } from '../../context/ThemeContext'

type CategoryType = string

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
  books: 'books',
}

const normalizeCategoryType = (value?: string): CategoryType => {
  if (!value) return 'medicines'
  const lower = value.toLowerCase()
  // Если есть алиас - возвращаем его, иначе возвращаем как есть (для поддержки новых категорий)
  return CATEGORY_ALIASES[lower] || lower
}

const resolveDetailEndpoint = (type: CategoryType, slug: string) => {
  switch (type) {
    case 'clothing':
      return `/api/catalog/clothing/products/${slug}`
    case 'shoes':
      return `/api/catalog/shoes/products/${slug}`
    case 'electronics':
      return `/api/catalog/electronics/products/${slug}`
    default:
      // Для всех остальных категорий (включая новые динамические) используем общий эндпоинт
      return `/api/catalog/products/${slug}`
  }
}

const parsePriceWithCurrency = (value?: string | number | null) => {
  if (value === null || typeof value === 'undefined') {
    return { price: null as string | number | null, currency: null as string | null }
  }
  if (typeof value === 'number') {
    return { price: value, currency: null as string | null }
  }
  const trimmed = value.trim()
  const match = trimmed.match(/^([0-9]+(?:[.,][0-9]+)?)\s*([A-Za-z]{3,5})$/)
  if (match) {
    return { price: match[1].replace(',', '.'), currency: match[2].toUpperCase() }
  }
  return { price: trimmed, currency: null as string | null }
}

const parseNumber = (value: string | number | null | undefined) => {
  if (value === null || typeof value === 'undefined') return null
  const normalized = String(value).replace(',', '.').replace(/[^0-9.]/g, '')
  if (!normalized) return null
  const num = Number(normalized)
  return Number.isFinite(num) ? num : null
}

const normalizeMediaValue = (value?: string | null) => {
  if (!value) return null
  const trimmed = String(value).trim()
  if (!trimmed) return null
  const lower = trimmed.toLowerCase()
  if (lower === 'null' || lower === 'none' || lower === 'undefined') return null
  return trimmed
}

interface Product {
  id: number
  name: string
  slug: string
  description: string
  price: string
  old_price?: string | number | null
  old_price_formatted?: string | null
  currency: string
  stock_quantity?: number | null
  main_image?: string
  main_image_url?: string
  video_url?: string
  images?: { id: number; image_url: string; video_url?: string | null; alt_text?: string; is_main?: boolean }[]
  sizes?: { id: number; size?: string; is_available?: boolean; stock_quantity?: number | null }[]
  variants?: Variant[]
  default_variant_slug?: string | null
  active_variant_slug?: string | null
  active_variant_price?: string | null
  active_variant_currency?: string | null
  active_variant_old_price_formatted?: string | null
  active_variant_stock_quantity?: number | null
  active_variant_main_image_url?: string | null
  translations?: ProductTranslation[]
  product_type?: string
  // SEO (с бэкенда — для книг и др.)
  meta_title?: string | null
  meta_description?: string | null
  og_title?: string | null
  og_description?: string | null
  og_image_url?: string | null
  // Книги
  isbn?: string | null
  publisher?: string | null
  publication_date?: string | null
  pages?: number | null
  language?: string | null
  cover_type?: string | null
  rating?: number | string | null
  reviews_count?: number | null
  is_bestseller?: boolean
  is_new?: boolean
  book_authors?: { id: number; author: { full_name: string } }[]
  weight_value?: number | string | null
  weight_unit?: string | null
  book_attributes?: { format?: string; thickness_mm?: string }
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

const resolveAvailableStock = (
  product: Product,
  selectedVariant: Variant | null | undefined,
  selectedSize: string | undefined
): number | null => {
  const sizeCandidate = selectedSize
    ? (selectedVariant?.sizes || product.sizes || []).find((s) => (s.size || '') === selectedSize)
    : undefined

  const sizeStock = sizeCandidate?.stock_quantity
  if (sizeStock !== null && sizeStock !== undefined) {
    return sizeStock
  }

  const variantStock = selectedVariant?.stock_quantity
  if (variantStock !== null && variantStock !== undefined) {
    return variantStock
  }

  const productStock = product.stock_quantity
  if (productStock !== null && productStock !== undefined) {
    return productStock
  }

  return null
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
  const router = useRouter()
  const { theme } = useTheme()
  const variants = product?.variants || []

  // Выбираем дефолтный вариант-цвет: активный, либо первый доступный
  const initialVariant =
    variants.find((v) => v.slug === product?.active_variant_slug) ||
    variants.find((v) => v.slug === product?.default_variant_slug) ||
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
  const sizesForColor = (selectedVariant?.sizes && selectedVariant.sizes.length > 0)
    ? selectedVariant.sizes
    : (product?.sizes || [])

  const maxAvailable = product ? resolveAvailableStock(product, selectedVariant, selectedSize) : null

  useEffect(() => {
    if (maxAvailable === 0) {
      setQuantity(1)
      return
    }
    if (maxAvailable !== null && quantity > maxAvailable) {
      setQuantity(Math.max(1, maxAvailable))
    }
  }, [maxAvailable, quantity])

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
        resolveMediaUrl(
          found.main_image ||
            found.images?.find((img) => img.is_main)?.image_url ||
            found.images?.[0]?.image_url ||
            product.active_variant_main_image_url ||
            product.main_image_url ||
            product.main_image ||
            gallerySourceLocal.find((img) => img.is_main)?.image_url ||
            gallerySourceLocal[0]?.image_url ||
            null
        ) || null
      )
    }
  }

  // Элемент галереи: обычное фото или плейсхолдер «Видео»
  type GalleryItem = { id: number | string; image_url: string; video_url?: string | null; alt_text?: string; is_main?: boolean; sort_order?: number; isVideo?: boolean }
  const buildGallerySource = (): GalleryItem[] => {
    if (!product) return []
    const variantImages = selectedVariant?.images || []
    const productImages = product.images || []
    const mainImageUrl = resolveMediaUrl(
      normalizeMediaValue(selectedVariant?.main_image) ||
        normalizeMediaValue(product.main_image_url) ||
        normalizeMediaValue(product.main_image)
    )
    const normalizedProductVideoUrl = normalizeMediaValue(product.video_url)
    const hasVideo = Boolean(normalizedProductVideoUrl && isVideoUrl(normalizedProductVideoUrl))
    const seenVideoUrls = new Set<string>()

    const baseImages: GalleryItem[] = (variantImages.length > 0 ? variantImages : productImages).flatMap((img) => {
      const imageUrl = normalizeMediaValue(img.image_url)
      const videoUrl = normalizeMediaValue((img as { video_url?: string | null }).video_url)
      if (videoUrl && isVideoUrl(videoUrl)) {
        if (seenVideoUrls.has(videoUrl)) {
          return []
        }
        seenVideoUrls.add(videoUrl)
        return [{
          id: `video-${img.id}`,
          image_url: imageUrl || '',
          video_url: videoUrl,
          alt_text: img.alt_text,
          is_main: img.is_main,
          sort_order: (img as { sort_order?: number }).sort_order,
          isVideo: true
        } as GalleryItem]
      }
      if (!imageUrl) {
        return []
      }
      return [{
        id: img.id,
        image_url: imageUrl,
        alt_text: img.alt_text,
        is_main: img.is_main,
        sort_order: (img as { sort_order?: number }).sort_order,
      } as GalleryItem]
    })
    let list: GalleryItem[] = []
    const hasMainInBase = baseImages.some((img) => img.is_main || resolveMediaUrl(img.image_url) === mainImageUrl)

    if (mainImageUrl && !hasMainInBase) {
      list = [{ id: 0, image_url: mainImageUrl, alt_text: product.name, is_main: true, sort_order: -1 }, ...baseImages]
    } else {
      list = baseImages
    }
    if (hasVideo && normalizedProductVideoUrl && !seenVideoUrls.has(normalizedProductVideoUrl)) {
      list = [{ id: 'main-video', image_url: '', video_url: normalizedProductVideoUrl, alt_text: 'Видео', isVideo: true, sort_order: -2 }, ...list]
    }
    return list
  }

  const gallerySource = buildGallerySource()
  const galleryMainImageUrl = normalizeMediaValue(
    gallerySource.find((img) => !img.isVideo && img.is_main)?.image_url ||
      gallerySource.find((img) => !img.isVideo && img.image_url)?.image_url
  )
  const initialImage =
    resolveMediaUrl(
      galleryMainImageUrl ||
        normalizeMediaValue(selectedVariant?.main_image) ||
        normalizeMediaValue(selectedVariant?.images?.find((img) => img.is_main)?.image_url) ||
        normalizeMediaValue(selectedVariant?.images?.[0]?.image_url) ||
        normalizeMediaValue(product?.active_variant_main_image_url || null) ||
        normalizeMediaValue(product?.main_image_url || null) ||
        normalizeMediaValue(product?.main_image || null) ||
        normalizeMediaValue(gallerySource.find((img) => !img.isVideo && img.image_url)?.image_url)
    ) || ''
  const hasImageSource = Boolean(
    normalizeMediaValue(selectedVariant?.main_image) ||
      selectedVariant?.images?.some((img) => normalizeMediaValue(img.image_url)) ||
      normalizeMediaValue(product?.main_image_url || null) ||
      normalizeMediaValue(product?.main_image || null) ||
      product?.images?.some((img) => normalizeMediaValue(img.image_url)) ||
      gallerySource.some((img) => !img.isVideo && normalizeMediaValue(img.image_url))
  )
  const [activeImage, setActiveImage] = useState<string | null>(initialImage || null)
  const initialVideoUrl =
    (product?.video_url && isVideoUrl(product.video_url) ? product.video_url : null) ||
    gallerySource.find((item) => item.isVideo && item.video_url)?.video_url ||
    null
  const [activeVideoUrl, setActiveVideoUrl] = useState<string | null>(initialVideoUrl)
  const [activeMediaType, setActiveMediaType] = useState<'video' | 'image'>(() =>
    !hasImageSource && initialVideoUrl ? 'video' : 'image'
  )

  // Обновляем главную картинку при изменении товара или варианта
  useEffect(() => {
    if (!product) return
    const currentGallerySource = selectedVariant?.images?.length ? selectedVariant.images : (product.images || [])
    const imageFromGallery =
      normalizeMediaValue(currentGallerySource.find((img) => img.is_main)?.image_url) ||
      normalizeMediaValue(currentGallerySource.find((img) => img.image_url)?.image_url)
    const newImage =
      resolveMediaUrl(
        imageFromGallery ||
          normalizeMediaValue(selectedVariant?.main_image) ||
          normalizeMediaValue(selectedVariant?.images?.find((img) => img.is_main)?.image_url) ||
          normalizeMediaValue(selectedVariant?.images?.[0]?.image_url) ||
          normalizeMediaValue(product.active_variant_main_image_url || null) ||
          normalizeMediaValue(product.main_image_url || null) ||
          normalizeMediaValue(product.main_image || null) ||
          normalizeMediaValue(currentGallerySource[0]?.image_url) ||
          null
      ) || null
    setActiveImage(newImage)
    const freshVideoUrl =
      (product.video_url && isVideoUrl(product.video_url) ? product.video_url : null) ||
      (currentGallerySource as { video_url?: string | null }[]).find((item) => item.video_url && isVideoUrl(item.video_url))?.video_url ||
      null
    setActiveVideoUrl(freshVideoUrl)
    const hasImages = Boolean(
      normalizeMediaValue(selectedVariant?.main_image) ||
        selectedVariant?.images?.some((img) => normalizeMediaValue(img.image_url)) ||
        normalizeMediaValue(product.main_image_url || null) ||
        normalizeMediaValue(product.main_image || null) ||
        (currentGallerySource as { image_url?: string | null }[]).some((img) => normalizeMediaValue(img.image_url))
    )
    setActiveMediaType(hasImages ? 'image' : (freshVideoUrl ? 'video' : 'image'))
  }, [product, selectedVariant, router.asPath])

  if (!product) {
    return <div className="mx-auto max-w-6xl p-6">{t('not_found', 'Товар не найден')}</div>
  }

  // Получаем числовое значение цены для расчетов
  const parsedActiveVariantPrice = parsePriceWithCurrency(product.active_variant_price ?? null)
  const priceValue = selectedVariant?.price 
    ? parseFloat(String(selectedVariant.price))
    : (product.active_variant_price ? parseFloat(String(product.active_variant_price)) : (product.price ? parseFloat(String(product.price)) : null))
  const currency =
    selectedVariant?.currency ||
    product.active_variant_currency ||
    parsedActiveVariantPrice.currency ||
    product.currency ||
    'USD'
  const oldPriceSource =
    product.active_variant_old_price_formatted ||
    product.old_price_formatted ||
    selectedVariant?.old_price ||
    product.old_price
  const { price: parsedOldPrice, currency: parsedOldCurrency } = parsePriceWithCurrency(
    oldPriceSource !== null && typeof oldPriceSource !== 'undefined' ? String(oldPriceSource) : null
  )
  const displayOldPrice = parsedOldCurrency && parsedOldCurrency !== currency ? null : (parsedOldPrice ?? oldPriceSource)
  const displayOldCurrency = parsedOldCurrency || currency
  const displayOldPriceLabel = displayOldPrice ? String(displayOldPrice) : null
  const displayOldCurrencyLabel = displayOldCurrency ? String(displayOldCurrency) : null
  const oldPriceValue = parseNumber(displayOldPrice)
  const discountPercent = priceValue !== null && oldPriceValue !== null && oldPriceValue > priceValue && oldPriceValue > 0
    ? Math.round(((oldPriceValue - priceValue) / oldPriceValue) * 100)
    : null
  
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
  const metaTitle = (product.meta_title || product.og_title || '').trim() || `${product.name} — PharmaTurk`
  const metaDescription = (product.meta_description || product.og_description || '').trim() || product.description?.slice(0, 200) || `${product.name} — ${t('buy_on_pharmaturk', 'купить на PharmaTurk')}`
  const ogImage = (product.og_image_url || '').trim() || activeImage || product.active_variant_main_image_url || product.main_image_url || product.main_image || '/product-placeholder.svg'
  const availability =
    selectedVariant?.is_available === false || selectedVariant?.stock_quantity === 0
      ? 'https://schema.org/OutOfStock'
      : 'https://schema.org/InStock'
  const priceForSchema = selectedVariant?.price || product.price || product.active_variant_price
  const currencyForSchema = selectedVariant?.currency || product.active_variant_currency || product.currency
  const productSchema = {
    '@context': 'https://schema.org',
    '@type': productType === 'books' ? 'Book' : 'Product',
    name: product.name,
    description: metaDescription,
    image: ogImage,
    ...(productType === 'books' && product.isbn && { isbn: product.isbn }),
    ...(productType === 'books' && product.book_authors?.length
      ? { author: product.book_authors.map((a) => ({ '@type': 'Person', name: a.author?.full_name })) }
      : {}),
    ...(productType === 'books' && product.publisher && { publisher: { '@type': 'Organization', name: product.publisher } }),
    ...(productType === 'books' && product.pages != null && { numberOfPages: product.pages }),
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
            {/* Миниатюры слева: видео (если есть) + фото */}
            {gallerySource.length > 0 && (
              <div className="flex flex-col gap-3 overflow-y-auto flex-shrink-0">
                {gallerySource.map((img) => {
                  const resolvedThumbnail = resolveMediaUrl(img.image_url)
                  const isVideoItem = (img as GalleryItem).isVideo === true
                  const isActive =
                    isVideoItem
                      ? activeMediaType === 'video' && Boolean(img.video_url && img.video_url === activeVideoUrl)
                      : activeMediaType === 'image' && activeImage === resolvedThumbnail
                  return (
                    <button
                      key={String(img.id)}
                      type="button"
                      className={`relative w-28 h-28 rounded-lg overflow-hidden border flex-shrink-0 ${isActive ? 'border-violet-500 ring-2 ring-violet-300' : 'border-gray-200 hover:border-gray-300'}`}
                      onClick={() => {
                        if (isVideoItem) {
                          setActiveMediaType('video')
                          if (img.video_url) {
                            setActiveVideoUrl(img.video_url)
                          }
                        } else {
                          setActiveMediaType('image')
                          setActiveImage(resolvedThumbnail || null)
                        }
                      }}
                    >
                      {isVideoItem && img.video_url ? (
                        <video
                          src={resolveMediaUrl(img.video_url)}
                          muted
                          playsInline
                          preload="metadata"
                          className="w-full h-full object-cover pointer-events-none"
                          aria-label={img.alt_text || product.name}
                        />
                      ) : (
                        /* eslint-disable-next-line @next/next/no-img-element */
                        <img
                          src={resolvedThumbnail}
                          alt={img.alt_text || product.name}
                          className="w-full h-full object-cover pointer-events-none"
                        />
                      )}
                      {isVideoItem && (
                        <span className="absolute inset-0 flex items-center justify-center bg-black/30 rounded-lg" aria-hidden>
                          <svg className="w-10 h-10 text-white drop-shadow" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M8 5v14l11-7z" />
                          </svg>
                        </span>
                      )}
                    </button>
                  )
                })}
              </div>
            )}
            {/* Главная область: видео или выбранное фото */}
            <div className="flex-1 h-full flex items-start justify-start rounded-xl">
              {activeMediaType === 'video' && activeVideoUrl && isVideoUrl(activeVideoUrl) ? (
                <video
                  key="product-video"
                  src={resolveMediaUrl(activeVideoUrl)}
                  controls
                  playsInline
                  muted
                  preload="metadata"
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
            {/* Блок «Книга»: автор, издательство, страницы, ISBN, язык, обложка, рейтинг */}
            {productType === 'books' && (
              <div 
                className="mt-3 space-y-1.5 text-sm"
                style={{ color: theme === 'dark' ? '#D1D5DB' : '#4B5563' }}
              >
                {product.book_authors && product.book_authors.length > 0 && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('author', 'Автор')}: </span>
                    {product.book_authors.map((a) => a.author?.full_name).filter(Boolean).join(', ')}
                  </p>
                )}
                {(product.publisher || product.pages) && (
                  <p>
                    {product.publisher}
                    {product.publisher && product.pages && ' · '}
                    {product.pages != null && `${product.pages} ${t('pages', 'стр.')}`}
                  </p>
                )}
                {product.isbn && (
                  <p>ISBN: {product.isbn}</p>
                )}
                {(product.language || product.cover_type) && (
                  <p>
                    {[product.language, product.cover_type ? getLocalizedCoverType(product.cover_type, t) : null].filter(Boolean).join(' · ')}
                  </p>
                )}
                {(product.weight_value != null && product.weight_value !== '') && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('book_weight', 'Вес')}: </span>
                    {String(product.weight_value)} {product.weight_unit || 'kg'}
                  </p>
                )}
                {(product.book_attributes?.thickness_mm) && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('book_thickness_mm', 'Толщина, мм')}: </span>
                    {product.book_attributes.thickness_mm}
                  </p>
                )}
                {(product.book_attributes?.format) && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('book_format', 'Формат')}: </span>
                    {product.book_attributes.format}
                  </p>
                )}
                {product.publication_date && (
                  <p>
                    <span className="font-medium" style={{ color: theme === 'dark' ? '#E5E7EB' : '#374151' }}>{t('book_publication_year', 'Год издания')}: </span>
                    {String(product.publication_date).slice(0, 4)}
                  </p>
                )}
                {(product.rating != null && product.rating !== '' && Number(product.rating) > 0) && (
                  <p className="flex items-center gap-2">
                    <span className="inline-flex items-center gap-0.5 text-amber-600">
                      <svg className="w-4 h-4 fill-current" viewBox="0 0 20 20"><path d="M10 15l-5.878 3.09 1.123-6.545L.489 6.91l6.572-.955L10 0l2.939 5.955 6.572.955-4.756 4.635 1.123 6.545z" /></svg>
                      {typeof product.rating === 'number' ? product.rating.toFixed(1) : String(product.rating)}
                    </span>
                    {product.reviews_count != null && product.reviews_count > 0 && (
                      <span style={{ color: theme === 'dark' ? '#9CA3AF' : '#6B7280' }}>
                        ({product.reviews_count} {t('reviews', 'отзывов')})
                      </span>
                    )}
                  </p>
                )}
                {(product.is_bestseller || product.is_new) && (
                  <div className="flex flex-wrap gap-2 mt-2">
                    {product.is_bestseller && (
                      <span className="rounded-md bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-700 dark:bg-orange-900/40 dark:text-orange-300">
                        {t('bestseller', 'Бестселлер')}
                      </span>
                    )}
                    {product.is_new && (
                      <span className="rounded-md bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/40 dark:text-green-300">
                        {t('new', 'Новинка')}
                      </span>
                    )}
                  </div>
                )}
              </div>
            )}
            <div className="mt-3 text-xl font-semibold text-red-600">
              {displayPrice || t('price_on_request')}
            </div>
            {displayOldPriceLabel && (
              <div className="mt-1 flex items-baseline gap-2">
                <div className="text-sm text-gray-400 line-through">
                  {displayOldCurrencyLabel
                    ? `${displayOldPriceLabel} ${displayOldCurrencyLabel}`
                    : displayOldPriceLabel}
                </div>
                {discountPercent !== null && (
                  <div className="text-sm font-semibold !text-red-600">-{discountPercent}%</div>
                )}
              </div>
            )}
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
                  onClick={() => {
                    if (maxAvailable !== null) {
                      setQuantity(Math.min(maxAvailable, quantity + 1))
                      return
                    }
                    setQuantity(quantity + 1)
                  }}
                  disabled={maxAvailable !== null && quantity >= maxAvailable}
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
                <div 
                  className="whitespace-pre-wrap leading-relaxed text-base"
                  style={{ color: theme === 'dark' ? '#F3F4F6' : '#111827' }}
                  dangerouslySetInnerHTML={{ __html: getLocalizedProductDescription(product.description, t, product.translations, router.locale) }}
                />
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
  // Извлекаем валюту из cookie
  const cookieHeader: string = ctx.req.headers.cookie || ''
  const currencyMatch = cookieHeader.match(/(?:^|;\s*)currency=([^;]+)/)
  const currency = currencyMatch ? currencyMatch[1] : 'RUB'
  
  const localePrefix = ctx.locale ? `/${ctx.locale}` : ''
  const baseProductTypes: CategoryType[] = [
    'medicines', 'supplements', 'medical-equipment',
    'furniture', 'tableware', 'accessories', 'jewelry',
    'underwear', 'headwear'
  ]

  const fetchProduct = (type: CategoryType, slug: string) =>
    axios.get(`${base}${resolveDetailEndpoint(type, slug)}`, {
      headers: {
        'X-Currency': currency,
        'Accept-Language': ctx.locale || 'en'
      }
    })

  const buildProps = async (res: any, type: CategoryType) => ({
    props: {
      ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])),
      product: res.data,
      productType: type,
      isBaseProduct: baseProductTypes.includes(type),
    },
  })

  if (slugParts.length === 1) {
    const probeTypes: CategoryType[] = ['clothing', 'shoes', 'electronics', 'furniture', 'medicines', 'books']
    for (const t of probeTypes) {
      try {
        const res = await fetchProduct(t, productSlug)
        const product = res.data
        const actualType = product.product_type || t

        if (actualType !== 'medicines') {
          return {
            redirect: {
              destination: `${localePrefix}/product/${actualType}/${productSlug}`,
              permanent: false,
            },
          }
        }
        return buildProps(res, 'medicines')
      } catch {
        continue
      }
    }
    return { notFound: true }
  }

  try {
    const res = await fetchProduct(categoryType, productSlug)
    const product = res.data
    const actualType = product.product_type

    // Если тип в URL не совпадает с реальным типом товара, делаем редирект
    // Исключаем случай, когда мы на /product/slug (categoryType='medicines' по дефолту для baseProductTypes)
    // Но если мы явно на /product/furniture/... а товар books, надо редиректить.
    if (actualType && actualType !== categoryType && categoryType !== 'medicines') {
         return {
            redirect: {
              destination: `${localePrefix}/product/${actualType}/${product.slug || productSlug}`,
              permanent: false,
            },
         }
    }

    const activeVariantSlug = res.data?.active_variant_slug
    const baseSlug = res.data?.slug
    if (activeVariantSlug && baseSlug && activeVariantSlug === productSlug && baseSlug !== productSlug) {
      return {
        redirect: {
          destination: `${localePrefix}/product/${categoryType}/${baseSlug}`,
          permanent: false,
        },
      }
    }
    return buildProps(res, categoryType)
  } catch (error) {
    const probeTypes: CategoryType[] = ['clothing', 'shoes', 'electronics', 'furniture', 'medicines', 'books']
    const typesToTry = probeTypes.filter((t) => t !== categoryType)

    for (const t of typesToTry) {
      const probeEndpoint = resolveDetailEndpoint(t, productSlug)
      try {
        const res = await axios.get(`${base}${probeEndpoint}`, {
          headers: {
            'X-Currency': currency,
            'Accept-Language': ctx.locale || 'en'
          }
        })
        const product = res.data
        const actualType = product.product_type || t

        return {
          redirect: {
            destination: `${localePrefix}/product/${actualType}/${productSlug}`,
            permanent: false,
          },
        }
      } catch {
        continue
      }
    }

    return { notFound: true }
  }
}
