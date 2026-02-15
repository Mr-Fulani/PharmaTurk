import Link from 'next/link'
import { useTranslation } from 'next-i18next'
import AddToCartButton from './AddToCartButton'
import FavoriteButton from './FavoriteButton'
import { resolveMediaUrl, isVideoUrl, getPlaceholderImageUrl } from '../lib/media'

interface ProductCardProps {
  id: number
  name: string
  slug: string
  price: string | null
  currency: string
  oldPrice?: string | number | null
  badge?: string | null
  rating?: number | null
  imageUrl?: string | null
  videoUrl?: string | null
  viewMode?: 'grid' | 'list'
  description?: string
  href?: string
  productType?: string
  isBaseProduct?: boolean
  // Поля специфичные для книг
  isbn?: string
  publisher?: string
  pages?: number
  language?: string
  authors?: Array<{id: number, author: {full_name: string}}>
  reviewsCount?: number
  isBestseller?: boolean
  isNew?: boolean
}

export default function ProductCard({ 
  id, 
  name, 
  slug, 
  price, 
  currency, 
  oldPrice, 
  badge, 
  rating, 
  imageUrl,
  videoUrl,
  viewMode = 'grid',
  description,
  href,
  productType = 'medicines',
  isBaseProduct = true,
  isbn,
  publisher,
  pages,
  language,
  authors,
  reviewsCount,
  isBestseller,
  isNew
}: ProductCardProps) {
  const { t } = useTranslation('common')
  
  const resolvedImage =
    imageUrl && !isVideoUrl(imageUrl) ? resolveMediaUrl(imageUrl) : null
  const resolvedVideoUrl = videoUrl && isVideoUrl(videoUrl)
    ? resolveMediaUrl(videoUrl)
    : imageUrl && isVideoUrl(imageUrl)
      ? resolveMediaUrl(imageUrl)
      : null
  const showVideo = Boolean(resolvedVideoUrl)
  const parseNumber = (value: string | number | null | undefined) => {
    if (value === null || typeof value === 'undefined') return null
    const normalized = String(value).replace(',', '.').replace(/[^0-9.]/g, '')
    if (!normalized) return null
    const num = Number(normalized)
    return Number.isFinite(num) ? num : null
  }
  const priceValue = parseNumber(price)
  const oldPriceValue = parseNumber(oldPrice)
  const discountPercent = priceValue !== null && oldPriceValue !== null && oldPriceValue > priceValue && oldPriceValue > 0
    ? Math.round(((oldPriceValue - priceValue) / oldPriceValue) * 100)
    : null

  if (viewMode === 'list') {
    return (
      <div className="group flex flex-col sm:flex-row gap-4 rounded-xl border border-gray-200 bg-white p-4 shadow-sm hover:shadow-lg transition-all duration-200 hover:-translate-y-1">
        <div className="relative w-full sm:w-48 h-48 flex-shrink-0">
          {showVideo ? (
            <video
              src={resolvedVideoUrl!}
              poster={resolvedImage || undefined}
              playsInline
              muted
              autoPlay
              loop
              preload="metadata"
              className="w-full h-full rounded-md object-cover"
            />
          ) : resolvedImage ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={resolvedImage}
              alt={name}
              className="w-full h-full rounded-md object-cover"
              onError={(e) => {
                e.currentTarget.src = getPlaceholderImageUrl({ type: 'product', id })
              }}
            />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={getPlaceholderImageUrl({ type: 'product', id })}
              alt="No image"
              className="w-full h-full rounded-md object-cover"
              onError={(e) => {
                e.currentTarget.src = '/product-placeholder.svg'
              }}
            />
          )}
          {badge && (
            <span className="absolute left-2 top-2 rounded-md bg-pink-100 px-2 py-0.5 text-xs font-medium text-pink-700 ring-1 ring-pink-200">
              {badge}
            </span>
          )}
        </div>
        <div className="flex-1 flex flex-col justify-between">
          <div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2 hover-text-warm transition-colors">{name}</h3>
            {description && (
              <p className="text-sm text-gray-600 line-clamp-2 mb-3">{description}</p>
            )}
            <div className="flex items-center gap-4 mb-3">
              <div className="flex items-baseline gap-2">
                <div className="text-lg font-bold text-[var(--text-strong)]">
                  {price ? `${price} ${currency}` : t('price_on_request', 'Цена по запросу')}
                </div>
                {oldPrice && (
                  <div className="text-sm text-gray-400 line-through">
                    {String(oldPrice).includes(currency) ? oldPrice : `${oldPrice} ${currency}`}
                  </div>
                )}
                {oldPrice && discountPercent !== null && (
                  <div className="text-sm font-semibold !text-red-600">-{discountPercent}%</div>
                )}
              </div>
              {typeof rating === 'number' && (
                <div className="flex items-center gap-1 text-sm text-amber-600">
                  <svg className="w-4 h-4 fill-current" viewBox="0 0 20 20">
                    <path d="M10 15l-5.878 3.09 1.123-6.545L.489 6.91l6.572-.955L10 0l2.939 5.955 6.572.955-4.756 4.635 1.123 6.545z" />
                  </svg>
                  <span>{rating.toFixed(1)}</span>
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href={href || `/product/${productType}/${slug}`}
              className="inline-flex items-center rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-800 hover:bg-violet-50 hover:border-violet-300 hover:text-violet-700 transition-colors"
            >
              {t('product_details', 'Подробнее')}
            </Link>
            <div className="flex items-center gap-2 ml-auto">
              <FavoriteButton 
                productId={id}
                productType={productType}
                iconOnly={true}
                className="!p-2 !rounded-full w-10 h-10 bg-white shadow-md hover:shadow-lg flex items-center justify-center hover:scale-110 transition-transform border border-gray-200"
              />
            <AddToCartButton 
              productId={isBaseProduct ? id : undefined} 
              productType={productType}
              productSlug={slug}
                className="!p-2 !rounded-full w-10 h-10 bg-white shadow-md hover:shadow-lg flex items-center justify-center hover:scale-110 transition-transform border border-gray-200"
                label=""
            />
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="group rounded-xl border border-gray-200 bg-white p-4 shadow-sm hover:shadow-lg transition-all duration-200 hover:-translate-y-1">
      <div className="relative">
        {showVideo ? (
          <video
            src={resolvedVideoUrl!}
            poster={resolvedImage || undefined}
            playsInline
            muted
            autoPlay
            loop
            preload="metadata"
            className="aspect-[4/3] w-full rounded-lg object-cover"
          />
        ) : resolvedImage ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={resolvedImage}
            alt={name}
            className="aspect-[4/3] w-full rounded-lg object-cover"
            onError={(e) => {
              e.currentTarget.src = getPlaceholderImageUrl({ type: 'product', id })
            }}
          />
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={getPlaceholderImageUrl({ type: 'product', id })}
            alt="No image"
            className="aspect-[4/3] w-full rounded-lg object-cover bg-gray-100"
            onError={(e) => {
              e.currentTarget.src = '/product-placeholder.svg'
            }}
          />
        )}
        {badge && (
          <span className="absolute left-2 top-2 rounded-md bg-pink-100 px-2 py-0.5 text-xs font-medium text-pink-700 ring-1 ring-pink-200">
            {badge}
          </span>
        )}
        {/* Бейджи для книг */}
        {productType === 'books' && (
          <>
            {isBestseller && (
              <span className="absolute left-2 top-2 rounded-md bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-700 ring-1 ring-orange-200">
                {t('bestseller', 'Бестселлер')}
              </span>
            )}
            {isNew && (
              <span className="absolute left-2 top-2 rounded-md bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700 ring-1 ring-green-200">
                {t('product_new', 'Новинка')}
              </span>
            )}
          </>
        )}
      </div>
      <h3 className="mt-3 line-clamp-2 text-base font-semibold text-gray-900 hover-text-warm transition-colors">
        {name}
      </h3>
      
      {/* Информация специфичная для книг */}
      {productType === 'books' && (
        <div className="mt-2 space-y-1">
          {authors && authors.length > 0 && (
            <p className="text-sm text-gray-600">
              {authors.map(a => a.author.full_name).join(', ')}
            </p>
          )}
          {(publisher || pages) && (
            <p className="text-xs text-gray-500">
              {publisher && `${publisher}`}
              {publisher && pages && ', '}
              {pages && `${pages} стр.`}
            </p>
          )}
          {isbn && (
            <p className="text-xs text-gray-500">ISBN: {isbn}</p>
          )}
        </div>
      )}
      <div className="mt-2 flex items-baseline gap-2">
        <div className="text-lg font-bold text-[var(--text-strong)]">
          {price ? `${price} ${currency}` : t('price_on_request', 'Цена по запросу')}
        </div>
        {oldPrice && (
          <div className="text-sm text-gray-400 line-through">
            {String(oldPrice).includes(currency) ? oldPrice : `${oldPrice} ${currency}`}
          </div>
        )}
        {oldPrice && discountPercent !== null && (
          <div className="text-sm font-semibold !text-red-600">-{discountPercent}%</div>
        )}
      </div>
      {typeof rating === 'number' && (
        <div className="mt-1 flex items-center gap-1 text-sm text-amber-600">
          <svg className="w-4 h-4 fill-current" viewBox="0 0 20 20">
            <path d="M10 15l-5.878 3.09 1.123-6.545L.489 6.91l6.572-.955L10 0l2.939 5.955 6.572.955-4.756 4.635 1.123 6.545z" />
          </svg>
          <span>{rating.toFixed(1)}</span>
          {productType === 'books' && reviewsCount && (
            <span className="text-gray-500">({reviewsCount})</span>
          )}
        </div>
      )}
      <div className="mt-3 flex items-center gap-2">
        <Link
          href={href || `/product/${productType}/${slug}`}
          className="inline-flex items-center rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-800 hover:bg-violet-50 hover:border-violet-300 hover:text-violet-700 transition-colors"
        >
          {t('product_details', 'Подробнее')}
        </Link>
        <div className="flex gap-2 ml-auto">
          <FavoriteButton 
            productId={id}
            productType={productType}
            iconOnly={true}
            className="!p-2 !rounded-full w-10 h-10 bg-white shadow-md hover:shadow-lg flex items-center justify-center hover:scale-110 transition-transform border border-gray-200"
          />
          <AddToCartButton 
            productId={isBaseProduct ? id : undefined} 
            productType={productType}
            productSlug={slug}
            className="!p-2 !rounded-full w-10 h-10 bg-white shadow-md hover:shadow-lg flex items-center justify-center hover:scale-110 transition-transform border border-gray-200"
            label=""
          />
        </div>
      </div>
    </div>
  )
}
