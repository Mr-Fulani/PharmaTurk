import { useState, useEffect } from 'react'
import { useTranslation } from 'next-i18next'
import { useFavoritesStore } from '../store/favorites'

interface FavoriteButtonProps {
  productId: number
  productType?: string
  className?: string
  iconOnly?: boolean
}

export default function FavoriteButton({
  productId,
  productType = 'medicines',
  className = '',
  iconOnly = false
}: FavoriteButtonProps) {
  const [loading, setLoading] = useState(false)
  const { isFavorite, add, remove } = useFavoritesStore()
  const { t } = useTranslation('common')
  const favorite = isFavorite(productId)

  const toggle = async () => {
    setLoading(true)
    try {
      if (favorite) {
        await remove(productId, productType)
      } else {
        await add(productId, productType)
      }
    } catch (error: any) {
      alert(error.message || t('favorite_error', 'Ошибка при работе с избранным'))
    } finally {
      setLoading(false)
    }
  }

  if (iconOnly) {
    return (
      <button
        onClick={toggle}
        disabled={loading}
        className={`inline-flex items-center justify-center rounded-full p-2 transition-all duration-200 ${
          favorite
            ? 'bg-red-100 text-red-600 hover:bg-red-200'
            : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
        } disabled:opacity-60 ${className}`}
        title={favorite ? t('remove_from_favorites', 'Удалить из избранного') : t('add_to_favorites', 'Добавить в избранное')}
      >
        {loading ? (
          <svg className="h-5 w-5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        ) : (
          <svg
            className={`h-5 w-5 ${favorite ? 'fill-current' : ''}`}
            fill={favorite ? 'currentColor' : 'none'}
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
        )}
      </button>
    )
  }

  return (
    <button
      onClick={toggle}
      disabled={loading}
      className={`inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 ${
        favorite
          ? 'bg-red-100 text-red-700 hover:bg-red-200'
          : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
      } disabled:opacity-60 ${className}`}
    >
      {loading ? (
        <>
          <svg className="h-4 w-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          <span>{t('processing', 'Обработка...')}</span>
        </>
      ) : (
        <>
          <svg
            className={`h-4 w-4 ${favorite ? 'fill-current' : ''}`}
            fill={favorite ? 'currentColor' : 'none'}
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
          <span>
            {favorite ? t('remove_from_favorites', 'Удалить из избранного') : t('add_to_favorites', 'В избранное')}
          </span>
        </>
      )}
    </button>
  )
}

