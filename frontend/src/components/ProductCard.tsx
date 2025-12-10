import Link from 'next/link'
import { useTranslation } from 'next-i18next'
import AddToCartButton from './AddToCartButton'
import FavoriteButton from './FavoriteButton'
import { resolveMediaUrl } from '../lib/media'

interface ProductCardProps {
  id: number
  name: string
  slug: string
  price: string | null
  currency: string
  oldPrice?: string | null
  badge?: string | null
  rating?: number | null
  imageUrl?: string | null
  viewMode?: 'grid' | 'list'
  description?: string
  href?: string
  productType?: string
  isBaseProduct?: boolean
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
  viewMode = 'grid',
  description,
  href,
  productType = 'medicines',
  isBaseProduct = true
}: ProductCardProps) {
  const { t } = useTranslation('common')
  
  const resolvedImage = resolveMediaUrl(imageUrl)

  if (viewMode === 'list') {
    return (
      <div className="group flex flex-col sm:flex-row gap-4 rounded-xl border border-gray-200 bg-white p-4 shadow-sm hover:shadow-lg transition-all duration-200 hover:-translate-y-1">
        <div className="relative w-full sm:w-48 h-48 flex-shrink-0">
          {resolvedImage ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={resolvedImage} alt={name} className="w-full h-full rounded-md object-cover" />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img src="/product-placeholder.svg" alt="No image" className="w-full h-full rounded-md object-cover" />
          )}
          {badge && (
            <span className="absolute left-2 top-2 rounded-md bg-pink-100 px-2 py-0.5 text-xs font-medium text-pink-700 ring-1 ring-pink-200">
              {badge}
            </span>
          )}
        </div>
        <div className="flex-1 flex flex-col justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2 group-hover:text-violet-700 transition-colors">{name}</h3>
            {description && (
              <p className="text-sm text-gray-600 line-clamp-2 mb-3">{description}</p>
            )}
            <div className="flex items-center gap-4 mb-3">
              <div className="flex items-baseline gap-2">
                <div className="text-lg font-bold text-violet-600">
                  {price ? `${price} ${currency}` : t('price_on_request', 'Цена по запросу')}
                </div>
                {oldPrice && (
                  <div className="text-sm text-gray-400 line-through">{oldPrice} {currency}</div>
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
        {resolvedImage ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={resolvedImage} alt={name} className="aspect-[4/3] w-full rounded-lg object-cover" />
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img src="/product-placeholder.svg" alt="No image" className="aspect-[4/3] w-full rounded-lg object-cover bg-gray-100" />
        )}
        {badge && (
          <span className="absolute left-2 top-2 rounded-md bg-pink-100 px-2 py-0.5 text-xs font-medium text-pink-700 ring-1 ring-pink-200">
            {badge}
          </span>
        )}
      </div>
      <h3 className="mt-3 line-clamp-2 text-base font-semibold text-gray-900 group-hover:text-violet-700 transition-colors">
        {name}
      </h3>
      <div className="mt-2 flex items-baseline gap-2">
        <div className="text-lg font-bold text-violet-600">
          {price ? `${price} ${currency}` : t('price_on_request', 'Цена по запросу')}
        </div>
        {oldPrice && (
          <div className="text-sm text-gray-400 line-through">{oldPrice} {currency}</div>
        )}
      </div>
      {typeof rating === 'number' && (
        <div className="mt-1 flex items-center gap-1 text-sm text-amber-600">
          <svg className="w-4 h-4 fill-current" viewBox="0 0 20 20">
            <path d="M10 15l-5.878 3.09 1.123-6.545L.489 6.91l6.572-.955L10 0l2.939 5.955 6.572.955-4.756 4.635 1.123 6.545z" />
          </svg>
          <span>{rating.toFixed(1)}</span>
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


