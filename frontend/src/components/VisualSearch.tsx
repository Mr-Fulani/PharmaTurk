'use client'

import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'next-i18next'
import api from '../lib/api'
import { buildProductIdentityKey, isBaseProductType } from '../lib/product'
import ProductCard from './ProductCard'
import { ProductTranslation } from '../lib/i18n'
import { ProductCardGalleryImage } from './ProductCardImageGallery'

const UPLOAD_TEMP_ENABLED = true // set true when /api/upload/temp/ exists
const MAX_IMAGE_BYTES = 5 * 1024 * 1024
const ALLOWED_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp'])

type ApiError = {
  code?: string
  message?: string
  response?: {
    status?: number
    data?: { error?: string; detail?: string }
  }
}

interface Product {
  id: number
  name: string
  slug: string
  price: string | number | null
  currency?: string | null
  old_price?: string | null
  main_image_url?: string | null
  main_image?: string | null
  images?: ProductCardGalleryImage[] | null
  video_url?: string | null
  main_video_url?: string | null
  main_gif_url?: string | null
  product_type?: string
  is_new?: boolean
  is_bestseller?: boolean
  is_featured?: boolean
  rating?: number | string | null
  reviews_count?: number | null
  translations?: ProductTranslation[]
  gender?: string | null
}

interface SearchResult {
  product_id: number
  similarity: number
  product: Product
}

/**
 * Visual search: upload image, get similar products from RecSys.
 */
export default function VisualSearch() {
  const { t, i18n } = useTranslation('common')
  const [searching, setSearching] = useState(false)
  const [results, setResults] = useState<SearchResult[]>([])
  const [error, setError] = useState<string | null>(null)
  const [urlInput, setUrlInput] = useState('')
  const activeRequest = useRef<AbortController | null>(null)

  useEffect(() => () => activeRequest.current?.abort(), [])

  const beginSearch = () => {
    activeRequest.current?.abort()
    const controller = new AbortController()
    activeRequest.current = controller
    setError(null)
    setSearching(true)
    setResults([])
    return controller
  }

  const finishSearch = (controller: AbortController) => {
    if (activeRequest.current === controller) {
      activeRequest.current = null
      setSearching(false)
    }
  }

  const requestVisualResults = async (url: string, controller: AbortController) => {
    const searchRes = await api.post('/recommendations/search_by_image/', {
      image_url: url.trim(),
      limit: 12,
    }, { signal: controller.signal })
    if (controller.signal.aborted) return
    const foundResults = searchRes.data.results || []
    setResults(foundResults)
    if (foundResults.length === 0) {
      setError(t('products_not_found', 'Товары не найдены'))
    }
  }

  const showRequestError = (err: unknown) => {
    const apiError = err as ApiError
    if (apiError.code === 'ERR_CANCELED') return
    const errorData = apiError.response?.data
    if (apiError.response?.status === 429) {
      setError(t('visual_search_rate_limited', 'Слишком много запросов. Подождите минуту и попробуйте снова.'))
    } else if (apiError.response?.status === 403) {
      setError(t('visual_search_forbidden', 'Не удалось отправить изображение. Обновите страницу и попробуйте снова.'))
    } else if (errorData?.error === 'invalid_image_url') {
      setError(t('invalid_image_url', 'Не удалось обработать URL. Ссылка должна вести прямо на JPEG, PNG или WebP.'))
    } else {
      const msg = errorData?.error || errorData?.detail || apiError.message || t('search_error', 'Ошибка поиска')
      setError(String(msg))
    }
    setResults([])
  }

  const cancelActiveSearch = () => {
    activeRequest.current?.abort()
    activeRequest.current = null
    setSearching(false)
  }

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) {
      cancelActiveSearch()
      setError(t('select_image', 'Выберите изображение'))
      return
    }
    if (!ALLOWED_IMAGE_TYPES.has(file.type)) {
      cancelActiveSearch()
      setError(t('unsupported_image_format', 'Поддерживаются только JPEG, PNG и WebP'))
      return
    }
    if (file.size > MAX_IMAGE_BYTES) {
      cancelActiveSearch()
      setError(t('image_too_large', 'Размер изображения не должен превышать 5 МБ'))
      return
    }
    const controller = beginSearch()
    try {
      if (UPLOAD_TEMP_ENABLED) {
        const formData = new FormData()
        formData.append('file', file)
        // Let Axios/browser set the multipart boundary; a manual Content-Type
        // can produce an unreadable upload on some browsers.
        const uploadRes = await api.post('/upload/temp/', formData, { signal: controller.signal })
        const imageUrl = uploadRes.data?.url || uploadRes.data?.image_url
        if (!imageUrl) {
          setError(t('upload_failed', 'Не удалось загрузить изображение. Используйте URL.'))
          return
        }
        await requestVisualResults(imageUrl, controller)
      } else {
        setError(t('upload_unavailable', 'Загрузка файла недоступна. Вставьте URL изображения ниже.'))
      }
    } catch (err: unknown) {
      showRequestError(err)
    } finally {
      finishSearch(controller)
    }
  }

  const handleUrlSearch = async (url: string) => {
    if (!url.trim()) return
    const controller = beginSearch()
    try {
      await requestVisualResults(url, controller)
    } catch (err: unknown) {
      showRequestError(err)
    } finally {
      finishSearch(controller)
    }
  }

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-6 bg-white dark:bg-gray-800">
      <h3 className="text-lg font-semibold mb-4 text-gray-900 dark:text-white">
        {t('visual_search', 'Поиск по фото')}
      </h3>
      <div className="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg p-6 text-center">
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          onChange={handleImageUpload}
          className="hidden"
          id="visual-search-file"
        />
        <label htmlFor="visual-search-file" className="cursor-pointer block">
          <span className="text-gray-600 dark:text-gray-400">
            {t('upload_image_search', 'Загрузите фото для поиска похожих товаров')}
          </span>
        </label>
      </div>
      <div className="mt-4">
        <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
          {t('or_paste_image_url', 'Или вставьте URL изображения')}
        </label>
        <div className="flex gap-2">
          <input
            type="url"
            value={urlInput}
            onChange={(e) => setUrlInput(e.target.value)}
            placeholder="https://..."
            className="flex-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-400 px-3 py-2 focus:ring-2 focus:ring-accent focus:border-accent"
          />
          <button
            type="button"
            onClick={() => handleUrlSearch(urlInput)}
            disabled={searching || !urlInput.trim()}
            className="rounded bg-gray-800 dark:bg-gray-200 text-white dark:text-gray-900 px-4 py-2 disabled:opacity-50"
          >
            {t('search', 'Искать')}
          </button>
        </div>
      </div>
      {searching && (
        <p className="mt-4 text-center text-gray-500">{t('searching', 'Ищем похожие...')}</p>
      )}
      {error && (
        <p className="mt-4 text-center text-red-500">{error}</p>
      )}
      {results.length > 0 && (
        <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-4">
          {results.map((r) => (
            <ProductCard
              key={buildProductIdentityKey(r.product, r.product.product_type)}
              id={r.product.id}
              baseProductId={(r.product as { base_product_id?: number }).base_product_id}
              name={r.product.name}
              slug={r.product.slug}
              price={r.product.price != null ? String(r.product.price) : null}
              currency={r.product.currency || 'RUB'}
              oldPrice={r.product.old_price != null ? String(r.product.old_price) : null}
              imageUrl={r.product.main_image_url || r.product.main_image}
              galleryImages={r.product.images}
              videoUrl={r.product.video_url}
              mainVideoUrl={r.product.main_video_url}
              mainGifUrl={r.product.main_gif_url}
              hasManualMainImage={(r.product as any).has_manual_main_image}
              productType={r.product.product_type || 'medicines'}
              isBaseProduct={isBaseProductType(r.product.product_type || 'medicines')}
              isBestseller={r.product.is_bestseller}
              isNew={r.product.is_new}
              isFeatured={r.product.is_featured}
              rating={r.product.rating}
              reviewsCount={r.product.reviews_count ?? undefined}
              translations={r.product.translations}
              locale={i18n.language}
            />
          ))}
        </div>
      )}
    </div>
  )
}
