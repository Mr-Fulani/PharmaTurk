import Link from 'next/link'
import dynamic from 'next/dynamic'
import { PointerEvent, useState } from 'react'
import { useTranslation } from 'next-i18next'
import { ChatBubbleOvalLeftIcon, StarIcon } from '@heroicons/react/20/solid'
import FavoriteButton from './FavoriteButton'
import ShareButton from './ShareButton'

const LazyYouTubeCard = dynamic(() => import('./LazyYouTubeCard'), { ssr: false })
import InViewAutoplayVideo from './InViewAutoplayVideo'
import InViewAmbientIframe from './InViewAmbientIframe'
import {
  resolveMediaUrl,
  isVideoUrl,
  getPlaceholderImageUrl,
  getVideoEmbedUrl,
  extractYouTubeId,
  getYouTubeCardThumbnailUrl,
  withListingImageMaxWidth,
  pickPreferredVideoUrl,
  isGifUrl,
  applyImageFallback,
} from '../lib/media'
import { buildProductUrl } from '../lib/urls'
import { buildFavoriteProductHref } from '../lib/favoriteLinks'
import { favoriteApiProductId } from '../lib/product'
import { formatMoney, getCurrencySymbol, parseMoneyNumber } from '../lib/price'
import { getLocalizedProductDescription, getLocalizedProductName, ProductTranslation } from '../lib/i18n'
import ProductCardImageGallery, { ProductCardGalleryImage } from './ProductCardImageGallery'

interface ProductCardProps {
  id: number
  baseProductId?: number
  favoriteId?: number
  name: string
  slug: string
  price: string | null
  currency: string
  oldPrice?: string | number | null
  badge?: string | null
  rating?: number | string | null
  brandName?: string | null
  imageUrl?: string | null
  galleryImages?: ProductCardGalleryImage[] | null
  videoUrl?: string | null
  /** Дублирует API main_video_url; вместе с video_url выбирается предпочтительный (proxy и т.д.). */
  mainVideoUrl?: string | null
  /** API main_gif_url (услуги и др.): после видео, до статичной картинки. */
  mainGifUrl?: string | null
  viewMode?: 'grid' | 'list'
  description?: string
  href?: string
  productType?: string
  isBaseProduct?: boolean
  translations?: ProductTranslation[]
  locale?: string
  // Поля специфичные для книг
  isbn?: string
  publisher?: string
  pages?: number
  language?: string
  authors?: Array<{ id: number, author: { full_name: string, full_name_en?: string } }>
  reviewsCount?: number
  isBestseller?: boolean
  isNew?: boolean
  isFeatured?: boolean
  meta_title?: string | null
  meta_description?: string | null
  meta_keywords?: string | null
  og_title?: string | null
  og_description?: string | null
  og_image_url?: string | null
  /**
   * has_manual_main_image с API: загружен файл главного фото — на витрине не подменяем превью на видео/GIF.
   */
  hasManualMainImage?: boolean
  imageFit?: 'cover' | 'contain' | 'lower-cover'
}

export default function ProductCard({
  id,
  baseProductId,
  favoriteId,
  name,
  slug,
  price,
  currency,
  oldPrice,
  badge,
  rating,
  brandName,
  imageUrl,
  galleryImages,
  videoUrl,
  mainVideoUrl,
  mainGifUrl,
  viewMode = 'grid',
  description,
  href,
  productType = 'medicines',
  isBaseProduct = true,
  translations,
  locale,
  isbn,
  publisher,
  pages,
  language,
  authors,
  reviewsCount,
  isBestseller,
  isNew,
  isFeatured,
  hasManualMainImage = false,
  imageFit = 'cover'
}: ProductCardProps) {
  const { t, i18n } = useTranslation('common')
  const [variantPreviewImage, setVariantPreviewImage] = useState<string | null>(null)
  const resetVariantPreview = (event: PointerEvent<HTMLDivElement>) => {
    if (event.pointerType === 'mouse') setVariantPreviewImage(null)
  }

  const localizedName = getLocalizedProductName(name, t, translations, locale || i18n.language)
  const rawDescription = getLocalizedProductDescription(
    description,
    t,
    translations,
    locale || i18n.language
  )
  const localizedDescription = rawDescription 
    ? rawDescription.replace(/<[^>]*>?/gm, '').replace(/&nbsp;/g, ' ').trim() 
    : ''

  const resolvedImage =
    imageUrl && !isVideoUrl(imageUrl) ? resolveMediaUrl(imageUrl) : null
  // На книгах обложка часто в файле (has_manual_main_image), но маркетинговое видео на витрине всё равно показываем.
  const preferStaticHero =
    Boolean(hasManualMainImage) &&
    (productType || '').toString().trim().replace(/_/g, '-').toLowerCase() !== 'books'
  const listingVideoRaw = preferStaticHero ? null : pickPreferredVideoUrl([mainVideoUrl, videoUrl])
  const resolvedVideoUrl = listingVideoRaw
    ? resolveMediaUrl(listingVideoRaw)
    : (!preferStaticHero && imageUrl && isVideoUrl(imageUrl))
      ? resolveMediaUrl(imageUrl)
      : null
  const showVideo = Boolean(resolvedVideoUrl)
  const youtubeIdForCard = showVideo && resolvedVideoUrl ? extractYouTubeId(resolvedVideoUrl) : null
  const ambientIframeSrc =
    showVideo && resolvedVideoUrl && !youtubeIdForCard
      ? getVideoEmbedUrl(resolvedVideoUrl, 'ambient')
      : null
  const hoverMediaClass = 'transition-transform duration-500 group-hover:scale-105'
  const imageFitClass = imageFit === 'contain'
    ? 'object-contain'
    : imageFit === 'lower-cover'
      ? 'object-cover object-[center_60%]'
      : 'object-cover'
  const listingImgSrc = resolvedImage ? withListingImageMaxWidth(resolvedImage) : null

  // Свотчи расцветок: бэкенд кладёт variant_slug в строки галереи вариативного товара.
  // Мини-фото каждой расцветки + клик ведёт на конкретный вариант (как в «Избранном»).
  // Путь без query: href из «Избранного» уже несёт ?active_variant_slug — не дублируем его в свотчах.
  const baseProductHref = (href || buildProductUrl(productType, slug)).split('?')[0]
  const variantSwatches = (galleryImages || [])
    .filter((img) => Boolean((img as { variant_slug?: string }).variant_slug))
    .map((img) => {
      const v = img as ProductCardGalleryImage & { variant_slug?: string; color?: string }
      const resolved = img.image_url ? resolveMediaUrl(img.image_url) : null
      return {
        slug: String(v.variant_slug || ''),
        color: String(v.color || ''),
        image: resolved ? withListingImageMaxWidth(resolved) : null,
      }
    })
    .filter((s) => s.slug && s.image)
  const MAX_SWATCHES = 5
  const visibleSwatches = variantSwatches.slice(0, MAX_SWATCHES)
  const extraSwatchCount = variantSwatches.length - visibleSwatches.length
  const swatchStrip = visibleSwatches.length > 1 ? (
    <div className="flex items-center gap-1.5 px-1">
      {visibleSwatches.map((sw) => (
        <Link
          key={sw.slug}
          href={buildFavoriteProductHref(baseProductHref, sw.slug)}
          title={sw.color || undefined}
          aria-label={sw.color || sw.slug}
          onPointerEnter={(event) => {
            if (event.pointerType === 'mouse') setVariantPreviewImage(sw.image!)
          }}
          onPointerMove={(event) => {
            if (event.pointerType === 'mouse') {
              setVariantPreviewImage((current) => current === sw.image ? current : sw.image!)
            }
          }}
          onFocus={() => setVariantPreviewImage(sw.image!)}
          onBlur={() => setVariantPreviewImage(null)}
          className="block h-6 w-6 overflow-hidden rounded-full border border-gray-200 transition-transform hover:scale-110 hover:border-[var(--accent)]"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={sw.image!}
            alt={sw.color || localizedName}
            loading="lazy"
            decoding="async"
            width={24}
            height={24}
            className="h-full w-full object-cover"
            onError={(event) => applyImageFallback(event.currentTarget)}
          />
        </Link>
      ))}
      {extraSwatchCount > 0 && (
        <span className="text-xs font-medium text-gray-500">+{extraSwatchCount}</span>
      )}
    </div>
  ) : null
  const rawGif = preferStaticHero || showVideo ? null : mainGifUrl
  const resolvedGifSrc =
    rawGif && isGifUrl(rawGif) ? withListingImageMaxWidth(resolveMediaUrl(rawGif)) : null
  const showGif = Boolean(resolvedGifSrc)
  const priceValue = parseMoneyNumber(price)
  const oldPriceValue = parseMoneyNumber(oldPrice)
  const discountPercent = priceValue !== null && oldPriceValue !== null && oldPriceValue > priceValue && oldPriceValue > 0
    ? Math.round(((oldPriceValue - priceValue) / oldPriceValue) * 100)
    : null
  const currentPriceColorClass =
    discountPercent !== null ? 'text-green-600 dark:text-green-400' : 'text-[var(--accent)]'
  const parsedRating = rating == null ? null : Number(rating)
  const displayRating = parsedRating !== null && Number.isFinite(parsedRating) && parsedRating > 0
    ? Math.min(5, parsedRating)
    : null
  const displayReviewsCount = typeof reviewsCount === 'number' && reviewsCount > 0
    ? reviewsCount
    : null
  const reviewsLabel = displayReviewsCount !== null
    ? t('product_reviews_count', {
        count: displayReviewsCount,
        formattedCount: new Intl.NumberFormat(locale || i18n.language).format(displayReviewsCount),
      })
    : t('product_reviews_title', 'Отзывы')
  const displayBrandName = brandName?.trim() || null
  const variantPreviewOverlay = variantPreviewImage ? (
    // Миниатюра варианта уже загружена в свотче, поэтому подмена не создаёт
    // отдельного API-запроса и не требует размонтировать видео под ней.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={variantPreviewImage}
      alt={localizedName}
      decoding="async"
      className={`pointer-events-none absolute inset-0 z-[5] h-full w-full ${imageFitClass}`}
    />
  ) : null

  const favoriteProductId = favoriteApiProductId(
    { id, base_product_id: baseProductId },
    productType
  )

  if (viewMode === 'list') {
    return (
      <div
        className="group flex flex-col sm:flex-row gap-4 rounded-xl border border-gray-200 bg-white p-4 shadow-sm hover:shadow-lg transition-all duration-200 hover:-translate-y-1"
        onPointerLeave={resetVariantPreview}
      >
        <div className="relative w-full sm:w-48 h-48 flex-shrink-0 overflow-hidden rounded-md">
          {/* Приоритет медиа: видео/youtube/ambient/gif выше галереи; галерея (с автосвайпом) — ниже */}
          {youtubeIdForCard ? (
            <LazyYouTubeCard
              youtubeId={youtubeIdForCard}
              youtubeThumb={getYouTubeCardThumbnailUrl(resolvedVideoUrl)}
              alt={localizedName}
              className="rounded-md"
            />
          ) : ambientIframeSrc ? (
            <InViewAmbientIframe
              src={ambientIframeSrc}
              title={localizedName}
              iframeClassName="rounded-md"
            />
          ) : showVideo && resolvedVideoUrl ? (
            <InViewAutoplayVideo
              src={resolvedVideoUrl}
              poster={resolvedImage || undefined}
              alt={localizedName}
              videoClassName="rounded-md"
              deferUntilInView
            />
          ) : showGif && resolvedGifSrc ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={resolvedGifSrc}
              alt={localizedName}
              loading="lazy"
              decoding="async"
              width={400}
              height={400}
              className={`w-full h-full rounded-md ${imageFitClass}`}
              onError={(event) => applyImageFallback(event.currentTarget)}
            />
          ) : listingImgSrc || galleryImages?.length ? (
            <ProductCardImageGallery
              productId={id}
              name={localizedName}
              mainImageUrl={listingImgSrc}
              images={galleryImages}
              previewImageUrl={variantPreviewImage}
              imageFitClass={imageFitClass}
              className="rounded-md overflow-hidden"
            />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={getPlaceholderImageUrl({ type: 'product', id })}
              alt="No image"
              loading="lazy"
              decoding="async"
              width={400}
              height={400}
              className={`w-full h-full rounded-md ${imageFitClass}`}
              onError={(event) => applyImageFallback(event.currentTarget)}
            />
          )}
          {variantPreviewOverlay}
          {badge && (
            <span className="absolute left-2 top-2 z-10 rounded-md bg-pink-100 px-2 py-0.5 text-xs font-medium text-pink-700 ring-1 ring-pink-200">
              {badge}
            </span>
          )}
          {/* Иконки в правом верхнем углу: избранное + шаринг */}
          <div
            className="absolute top-2 right-2 z-10 flex flex-col gap-1.5"
            onClick={(e) => { e.preventDefault(); e.stopPropagation() }}
          >
            <FavoriteButton
              productId={favoriteProductId}
              productType={productType}
              productSlug={slug}
              favoriteId={favoriteId}
              cornerIcon={true}
            />
            <ShareButton
              title={localizedName}
              description={localizedDescription || undefined}
              imageUrl={resolvedImage}
              slug={slug}
              productType={productType}
              cornerIcon={true}
            />
          </div>
        </div>
        <div className="flex-1 flex flex-col justify-between">
          <div>
            <h3 className="text-lg font-semibold text-[var(--text-strong)] mb-2 hover-text-warm transition-colors">{localizedName}</h3>
            {localizedDescription && (
              <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2 mb-3">{localizedDescription}</p>
            )}
            <div className="flex items-center gap-4 mb-3">
              <div className="flex items-baseline gap-2">
                <div className={`inline-flex items-center gap-1 text-lg font-bold ${currentPriceColorClass}`}>
                  {price ? (
                    <>
                      {formatMoney(price, currency, locale || i18n.language)}
                      <span>{getCurrencySymbol(currency)}</span>
                    </>
                  ) : t('price_on_request', 'Цена по запросу')}
                </div>
                {oldPrice && (
                  <div className="inline-flex items-center gap-1 text-sm text-gray-400">
                    <span className="line-through">
                      {formatMoney(oldPrice, currency, locale || i18n.language)}
                    </span>
                    <span>{getCurrencySymbol(currency)}</span>
                  </div>
                )}
                {oldPrice && discountPercent !== null && (
                  <div className="text-sm font-semibold !text-red-600">-{discountPercent}%</div>
                )}
              </div>
              {displayRating !== null && (
                <div className="flex items-center gap-1 text-sm text-amber-600">
                  <svg className="w-4 h-4 fill-current" viewBox="0 0 20 20">
                    <path d="M10 15l-5.878 3.09 1.123-6.545L.489 6.91l6.572-.955L10 0l2.939 5.955 6.572.955-4.756 4.635 1.123 6.545z" />
                  </svg>
                  <span>{displayRating.toFixed(1)}</span>
                </div>
              )}
              <div className="inline-flex items-center gap-1 text-sm text-[var(--text-weak)]">
                <ChatBubbleOvalLeftIcon className="h-4 w-4 text-gray-400 dark:text-gray-500" aria-hidden="true" />
                <span>{reviewsLabel}</span>
              </div>
              {displayBrandName && (
                <span
                  className="ml-auto max-w-[45%] truncate text-xs font-semibold text-[var(--accent)]"
                  title={displayBrandName}
                >
                  {displayBrandName}
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3">
            {/* Свотчи расцветок: мини-фото вариантов + переход на конкретную расцветку */}
            {swatchStrip}
            <Link
              href={href || buildProductUrl(productType, slug)}
              className="ml-auto inline-flex items-center rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-800 hover:bg-violet-50 hover:border-violet-300 hover:text-violet-700 transition-colors"
            >
              {t('product_details', 'Подробнее')}
            </Link>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div
      className="group relative flex h-full flex-col gap-2 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-2 shadow-[0_2px_10px_rgba(15,23,42,0.08)] transition-all duration-300 hover:-translate-y-1 hover:border-gray-300 hover:shadow-[0_12px_28px_rgba(15,23,42,0.16)] dark:hover:border-gray-600"
      onPointerLeave={resetVariantPreview}
    >
      <Link 
        href={href || buildProductUrl(productType, slug)}
        className="relative block w-full aspect-[4/5] rounded-xl overflow-hidden bg-gray-100/50"
      >
        {/* Приоритет медиа: видео/youtube/ambient/gif выше галереи; галерея (с автосвайпом) — ниже */}
        {youtubeIdForCard ? (
          <LazyYouTubeCard
            youtubeId={youtubeIdForCard}
            youtubeThumb={getYouTubeCardThumbnailUrl(resolvedVideoUrl)}
            alt={localizedName}
            className={hoverMediaClass}
          />
        ) : ambientIframeSrc ? (
          <InViewAmbientIframe
            src={ambientIframeSrc}
            title={localizedName}
            className="absolute inset-0 h-full w-full"
            iframeClassName={hoverMediaClass}
          />
        ) : showVideo && resolvedVideoUrl ? (
          <InViewAutoplayVideo
            src={resolvedVideoUrl}
            poster={resolvedImage || undefined}
            alt={localizedName}
            videoClassName={hoverMediaClass}
            deferUntilInView
          />
        ) : showGif && resolvedGifSrc ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={resolvedGifSrc}
            alt={localizedName}
            loading="lazy"
            decoding="async"
            width={400}
            height={500}
            className={`w-full h-full ${imageFitClass} ${hoverMediaClass}`}
            onError={(event) => applyImageFallback(event.currentTarget)}
          />
        ) : listingImgSrc || galleryImages?.length ? (
          <ProductCardImageGallery
            productId={id}
            name={localizedName}
            mainImageUrl={listingImgSrc}
            images={galleryImages}
            previewImageUrl={variantPreviewImage}
            imageFitClass={imageFitClass}
          />
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={getPlaceholderImageUrl({ type: 'product', id })}
            alt="No image"
            loading="lazy"
            decoding="async"
            width={400}
            height={500}
            className={`w-full h-full ${imageFitClass} transition-transform duration-500 group-hover:scale-105`}
            onError={(event) => applyImageFallback(event.currentTarget)}
          />
        )}
        {variantPreviewOverlay}
        
        {(badge || isFeatured || isNew || (productType === 'books' && isBestseller)) && (
          <div className="absolute left-2 top-2 flex flex-col gap-1 z-10">
            {badge && (
              <span className="rounded-md bg-pink-100/90 backdrop-blur-sm px-2 py-0.5 text-xs font-medium text-pink-700 ring-1 ring-pink-200">
                {badge}
              </span>
            )}
            {isFeatured && !badge && (
              <span className="rounded-md bg-pink-100/90 backdrop-blur-sm px-2 py-0.5 text-xs font-medium text-pink-700 ring-1 ring-pink-200">
                {t('product_featured', 'Хит')}
              </span>
            )}
            {productType === 'books' && isBestseller && (
              <span className="rounded-md bg-orange-100/90 backdrop-blur-sm px-2 py-0.5 text-xs font-medium text-orange-700 ring-1 ring-orange-200">
                {t('bestseller', 'Бестселлер')}
              </span>
            )}
            {isNew && (
              <span className="rounded-md bg-green-100/90 backdrop-blur-sm px-2 py-0.5 text-xs font-medium text-green-700 ring-1 ring-green-200">
                {t('product_new', 'Новинка')}
              </span>
            )}
          </div>
        )}

        {/* Иконки в правом верхнем углу: избранное + шаринг */}
        <div
          className="absolute top-2 right-2 z-20 flex flex-col gap-1.5"
          onClick={(e) => { e.preventDefault(); e.stopPropagation() }}
        >
          <FavoriteButton
            productId={favoriteProductId}
            productType={productType}
            productSlug={slug}
            favoriteId={favoriteId}
            cornerIcon={true}
          />
          <ShareButton
            title={localizedName}
            description={localizedDescription || undefined}
            imageUrl={resolvedImage}
            slug={slug}
            productType={productType}
            cornerIcon={true}
          />
        </div>
      </Link>

      {/* Свотчи расцветок: мини-фото вариантов + переход на конкретную расцветку */}
      {swatchStrip}

      {/* Цена, название и рейтинг */}
      <Link
        href={href || buildProductUrl(productType, slug)}
        className="flex flex-1 flex-col px-1 pb-1"
      >
        <div className="mb-1 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <span
            className={`inline-flex items-center gap-1 text-base md:text-lg font-bold leading-tight tracking-tight ${currentPriceColorClass}`}
          >
            {price ? (
              <>
                {formatMoney(price, currency, locale || i18n.language)}
                <span>{getCurrencySymbol(currency)}</span>
              </>
            ) : t('price_on_request', 'Цена по запросу')}
          </span>
          {oldPrice && (
            <span className="inline-flex items-center gap-1 text-xs md:text-sm text-gray-400">
              <span className="line-through">
                {formatMoney(oldPrice, currency, locale || i18n.language)}
              </span>
              <span>{getCurrencySymbol(currency)}</span>
            </span>
          )}
          {oldPrice && discountPercent !== null && (
            <span className="text-xs font-semibold !text-red-500">-{discountPercent}%</span>
          )}
        </div>
        
        <h3 className="line-clamp-2 min-h-[2.5rem] text-sm font-medium leading-5 text-[var(--text-strong)]">
          {localizedName}
        </h3>

        {/* Информация специфичная для книг */}
        {productType === 'books' && (
          <div className="mt-1 space-y-0.5">
            {authors && authors.length > 0 && (
              <p className="text-xs text-gray-500 line-clamp-1">
                {authors.map(a => {
                  const localeKey = (locale || '').toLowerCase()
                  const isEnglish = localeKey.startsWith('en')
                  return isEnglish ? (a.author.full_name_en || a.author.full_name) : a.author.full_name
                }).join(', ')}
              </p>
            )}
            {(publisher || pages) && (
              <p className="text-[10px] text-gray-400">
                {publisher && `${publisher}`}
                {publisher && pages && ', '}
                {pages && `${pages} стр.`}
              </p>
            )}
          </div>
        )}

        <div className="mt-auto flex min-h-5 items-center gap-1.5 pt-2 text-xs">
          {displayRating !== null && (
            <>
              <StarIcon className="h-4 w-4 flex-none text-amber-400" aria-hidden="true" />
              <span className="font-semibold text-[var(--text-strong)]">{displayRating.toFixed(1)}</span>
            </>
          )}
          <span className={`${displayRating !== null ? 'ml-1' : ''} inline-flex items-center gap-1 text-[var(--text-weak)]`}>
            <ChatBubbleOvalLeftIcon className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500" aria-hidden="true" />
            {reviewsLabel}
          </span>
          {displayBrandName && (
            <span
              className="ml-auto max-w-[55%] truncate text-right font-semibold text-[var(--accent)]"
              title={displayBrandName}
            >
              {displayBrandName}
            </span>
          )}
        </div>
      </Link>
    </div>
  )
}
