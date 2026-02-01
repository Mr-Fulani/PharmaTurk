import Head from 'next/head'
import { useEffect, useRef } from 'react'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { GetServerSideProps } from 'next'
import Link from 'next/link'
import Cookies from 'js-cookie'
import { useFavoritesStore } from '../store/favorites'
import ProductCard from '../components/ProductCard'

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

export default function FavoritesPage() {
  const { t } = useTranslation('common')
  const { favorites, loading, refresh } = useFavoritesStore()
  const refreshedRef = useRef(false)

  useEffect(() => {
    // Загружаем избранное только один раз при монтировании
    if (!refreshedRef.current) {
      refreshedRef.current = true
      const currentCurrency = Cookies.get('currency')
      refresh(currentCurrency)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <>
      <Head>
        <title>{t('favorites_title', 'Избранное')} — Turk-Export</title>
      </Head>
      <main className="mx-auto max-w-6xl p-6">
        <h1 className="mb-6 text-3xl font-bold text-gray-900">
          {t('favorites_title', 'Избранное')}
        </h1>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <svg className="h-8 w-8 animate-spin text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </div>
        ) : favorites.length === 0 ? (
          <div className="rounded-xl border border-gray-200 bg-white p-12 text-center shadow-sm">
            <svg
              className="mx-auto h-16 w-16 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"
              />
            </svg>
            <h2 className="mt-4 text-xl font-semibold text-gray-900">
              {t('favorites_empty_title', 'Избранное пусто')}
            </h2>
            <p className="mt-2 text-gray-600">
              {t('favorites_empty_description', 'Добавьте товары в избранное, чтобы не потерять их')}
            </p>
            <Link
              href="/"
              className="mt-6 inline-block rounded-md bg-red-600 px-6 py-3 font-medium text-white transition-all duration-200 hover:bg-red-700 hover:shadow-lg"
            >
              {t('favorites_go_shopping', 'Перейти к покупкам')}
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {favorites.map((favorite) => {
              const product = favorite.product
              const productType = product._product_type || 'medicines'
              const baseProductTypes = [
                'medicines',
                'supplements',
                'medical-equipment',
                'medical_equipment',
                'furniture',
                'tableware',
                'accessories',
                'jewelry',
                'underwear',
                'headwear',
              ]
              const isBaseProduct = baseProductTypes.includes(productType)
              const productHref = isBaseProduct 
                ? `/product/${product.slug}` 
                : `/product/${productType}/${product.slug}`
              const { price: parsedVariantPrice, currency: parsedVariantCurrency } = parsePriceWithCurrency(product.active_variant_price)
              const { price: parsedOldPrice, currency: parsedOldCurrency } = parsePriceWithCurrency(
                product.active_variant_old_price_formatted || product.old_price_formatted || product.old_price
              )
              const displayPrice = parsedVariantPrice ?? product.price
              const displayCurrency = product.active_variant_currency || parsedVariantCurrency || product.currency
              const displayOldCurrency = parsedOldCurrency || displayCurrency
              const displayOldPrice = displayOldCurrency === displayCurrency ? parsedOldPrice ?? product.old_price : null
              
              return (
                <ProductCard
                  key={favorite.id}
                  id={product.id}
                  name={product.name}
                  slug={product.slug}
                  price={displayPrice ? String(displayPrice) : null}
                  currency={displayCurrency || undefined}
                  oldPrice={displayOldPrice ? String(displayOldPrice) : null}
                  imageUrl={product.main_image_url}
                  href={productHref}
                  productType={productType}
                  isBaseProduct={isBaseProduct}
                />
              )
            })}
          </div>
        )}
      </main>
    </>
  )
}

export const getServerSideProps: GetServerSideProps = async (ctx) => {
  return {
    props: {
      ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])),
    },
  }
}
