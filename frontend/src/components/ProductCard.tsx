import Link from 'next/link'
import { useTranslation } from 'next-i18next'
import AddToCartButton from './AddToCartButton'

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
}

export default function ProductCard({ id, name, slug, price, currency, oldPrice, badge, rating, imageUrl }: ProductCardProps) {
  const { t } = useTranslation('common')
  return (
    <div className="group rounded-xl border border-gray-200 bg-white p-4 shadow-sm hover:shadow-md transition-shadow">
      <div className="relative">
        {imageUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={imageUrl} alt={name} className="aspect-[4/3] w-full rounded-md object-cover" />
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img src="/product-placeholder.svg" alt="No image" className="aspect-[4/3] w-full rounded-md object-cover" />
        )}
        {badge ? (
          <span className="absolute left-2 top-2 rounded-md bg-pink-100 px-2 py-0.5 text-xs font-medium text-pink-700 ring-1 ring-pink-200">{badge}</span>
        ) : null}
        
        {/* Cart Icon Button */}
        <div className="absolute right-2 bottom-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
          <AddToCartButton 
            productId={id} 
            className="!p-2 !rounded-full w-10 h-10 shadow-md hover:shadow-lg flex items-center justify-center"
            label=""
          />
        </div>
      </div>
      <h3 className="mt-3 line-clamp-2 text-base font-semibold text-gray-900">{name}</h3>
      <div className="mt-1 flex items-baseline gap-2">
        <div className="text-sm font-semibold text-gray-900">{price ? `${price} ${currency}` : t('price_on_request', 'Цена по запросу')}</div>
        {oldPrice ? <div className="text-xs text-gray-400 line-through">{oldPrice} {currency}</div> : null}
      </div>
      {typeof rating === 'number' ? (
        <div className="mt-1 text-xs text-amber-600">★ {rating.toFixed(1)}</div>
      ) : null}
      <div className="mt-3">
        <Link
          href={`/product/${slug}`}
          className="inline-flex items-center rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-800 hover:bg-gray-50"
        >
          {t('product_details', 'Подробнее')}
        </Link>
      </div>
    </div>
  )
}


