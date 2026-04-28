import { useState } from 'react'
import { useTranslation } from 'next-i18next'
import { shallow } from 'zustand/shallow'
import { useFavoritesStore, FavoriteVariantOpts } from '../store/favorites'

interface FavoriteButtonProps {
  /** Для карточек без вариантного slug (листинги) */
  productId?: number
  productType?: string
  /** Fallback для сопоставления после refresh, если список избранного вернул другой публичный id. */
  productSlug?: string
  /** Как product_slug при добавлении в корзину: вариант мебели / обуви / одежды */
  favoriteProductSlug?: string
  /** Размер для обуви/одежды (как в корзине) */
  favoriteSize?: string
  className?: string
  iconOnly?: boolean
  /** Режим угловой иконки: полупрозрачный фон, увеличенное сердечко */
  cornerIcon?: boolean
}

export default function FavoriteButton({
  productId,
  productType = 'medicines',
  productSlug,
  favoriteProductSlug,
  favoriteSize,
  className = '',
  iconOnly = false,
  cornerIcon = false,
}: FavoriteButtonProps) {
  const [loading, setLoading] = useState(false)
  const { favorites, isFavorite: isFavoriteFn, add, remove, refresh } = useFavoritesStore(
    (s) => ({
      favorites: s.favorites,
      isFavorite: s.isFavorite,
      add: s.add,
      remove: s.remove,
      refresh: s.refresh,
    }),
    shallow
  )
  const { t } = useTranslation('common')

  const variantOpts: FavoriteVariantOpts | undefined = favoriteProductSlug
    ? { productSlug: favoriteProductSlug, size: favoriteSize || '' }
    : undefined

  const favorite = isFavoriteFn(productId, productType, variantOpts, productSlug)

  const toggle = async (e?: React.MouseEvent) => {
    if (e) {
      e.preventDefault()
      e.stopPropagation()
    }
    setLoading(true)
    try {
      if (favorite) {
        await remove(productId, productType, variantOpts)
      } else {
        await add(productId, productType, variantOpts)
      }
    } catch (error: any) {
      const msg = String(error?.message || '')
      const already =
        /уже в избранном/i.test(msg) ||
        /already in favorites/i.test(msg) ||
        error?.response?.data?.detail === 'Товар уже в избранном'
      if (!favorite && already) {
        await refresh()
        return
      }
      alert(error.message || t('favorite_error', 'Ошибка при работе с избранным'))
    } finally {
      setLoading(false)
    }
  }

  // Режим угловой иконки — только сердечко, стеклянный стиль
  if (cornerIcon) {
    return (
      <button
        onClick={(e) => toggle(e)}
        disabled={loading}
        title={favorite ? t('remove_from_favorites', 'Удалить из избранного') : t('add_to_favorites', 'В избранное')}
        aria-label={favorite ? t('remove_from_favorites', 'Удалить из избранного') : t('add_to_favorites', 'В избранное')}
        className={`group flex items-center justify-center transition-all duration-200 disabled:opacity-60 ${className}`}
        style={{
          width: 36,
          height: 36,
          borderRadius: '50%',
          background: favorite ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.75)',
          backdropFilter: 'blur(6px)',
          WebkitBackdropFilter: 'blur(6px)',
          border: favorite ? '1.5px solid rgba(239,68,68,0.35)' : '1.5px solid rgba(255,255,255,0.6)',
          boxShadow: '0 2px 8px rgba(0,0,0,0.13)',
        }}
      >
        {loading ? (
          <svg
            style={{ width: 18, height: 18, animation: 'spin 1s linear infinite', color: favorite ? '#ef4444' : '#9ca3af' }}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        ) : (
          <svg
            style={{
              width: 18,
              height: 18,
              color: favorite ? '#ef4444' : '#6b7280',
              fill: favorite ? '#ef4444' : 'none',
              stroke: favorite ? '#ef4444' : 'currentColor',
              transition: 'all 0.2s',
            }}
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

  if (iconOnly) {
    return (
      <button
        onClick={(e) => toggle(e)}
        disabled={loading}
        className={`inline-flex items-center justify-center rounded-full p-2 transition-all duration-200 ${favorite
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
      onClick={(e) => toggle(e)}
      disabled={loading}
      className={`inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 ${favorite
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
