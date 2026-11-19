import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useTranslation } from 'next-i18next'
import { getSingleFlight } from '../lib/api'
import { getPlaceholderImageUrl, resolveMediaUrl } from '../lib/media'
import { buildProductUrl } from '../lib/urls'
import { getLocalizedProductName, ProductTranslation } from '../lib/i18n'
import { formatPrice, getCurrencySymbol, parsePriceWithCurrency } from '../lib/price'

interface ReferenceMedicine {
  id: number
  name: string
  slug: string
  price?: string | number | null
  currency?: string | null
  main_image_url?: string | null
  active_ingredient?: string | null
  translations?: ProductTranslation[]
}

/**
 * Справочный блок главной: лекарства с галочкой «Рекомендуемый» в админке.
 * Это не витрина: без «хит», «купить», «заказать» и без кнопки «В заявку» —
 * карточка только ведёт на страницу препарата (docs/HOME_BLOCKS.md).
 */
export default function MedicineReferenceBlock() {
  const { t, i18n } = useTranslation('common')
  const [medicines, setMedicines] = useState<ReferenceMedicine[]>([])

  useEffect(() => {
    getSingleFlight('/catalog/products/medicine-reference', { params: { limit: 8, view: 'card' } })
      .then((response) => setMedicines(Array.isArray(response.data) ? response.data : []))
      .catch((error) => console.error('Failed to fetch reference medicines:', error))
  }, [])

  if (medicines.length === 0) return null

  return (
    <section className="py-12" data-analytics-placement="home_medicine_reference">
      <div className="mx-auto max-w-page px-4">
        <h2 className="text-2xl md:text-3xl font-bold text-main mb-2 text-center">
          {t('medicine_reference_title', 'Часто ищут в справочнике лекарств')}
        </h2>
        <p className="mb-8 text-center text-sm text-[var(--text-weak)]">
          {t('medicine_reference_subtitle', 'Инструкции, аналоги и справочные цены в Турции')}
        </p>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {medicines.map((medicine) => {
            const name = getLocalizedProductName(medicine.name, t, medicine.translations, i18n.language)
            const { price, currency: parsedCurrency } = parsePriceWithCurrency(medicine.price)
            const currency = parsedCurrency || medicine.currency
            const priceLabel = price ? formatPrice(price, currency, i18n.language) : null
            return (
              <Link
                key={medicine.id}
                href={buildProductUrl('medicines', medicine.slug)}
                className="flex flex-col gap-2 rounded-[var(--card-radius)] border border-[var(--border)] bg-[var(--card-bg)] p-2 transition-colors duration-200 hover:border-[var(--accent)]"
              >
                <div className="aspect-[4/3] overflow-hidden rounded-[calc(var(--card-radius)-4px)] bg-gray-100/50">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={
                      (medicine.main_image_url ? resolveMediaUrl(medicine.main_image_url) : null) ||
                      getPlaceholderImageUrl({ type: 'product', id: medicine.id })
                    }
                    alt={name}
                    loading="lazy"
                    decoding="async"
                    width={400}
                    height={300}
                    className="h-full w-full object-contain"
                  />
                </div>
                <div className="flex flex-1 flex-col px-1 pb-1">
                  <h3 className="line-clamp-2 min-h-[2.5rem] text-sm font-medium leading-5 text-[var(--text-strong)]">
                    {name}
                  </h3>
                  {medicine.active_ingredient && (
                    <p className="mt-1 line-clamp-1 text-xs text-[var(--text-weak)]">{medicine.active_ingredient}</p>
                  )}
                  {priceLabel && (
                    <p className="mt-auto pt-2 text-xs text-[var(--text-weak)]">
                      {t('medicine_reference_price', 'Справочная цена в Турции')}:{' '}
                      <span className="font-semibold text-[var(--text-strong)]">
                        {priceLabel}
                        {currency ? ` ${getCurrencySymbol(String(currency))}` : ''}
                      </span>
                    </p>
                  )}
                </div>
              </Link>
            )
          })}
        </div>
        <div className="mt-6 text-center">
          <Link href="/categories/medicines" className="text-sm font-semibold text-[var(--accent)] hover:underline">
            {t('medicine_reference_all', 'Весь справочник лекарств')}
          </Link>
        </div>
      </div>
    </section>
  )
}
