'use client'

import { useState } from 'react'
import { useTranslation } from 'next-i18next'
import api from '../lib/api'
import { isBaseProductType } from '../lib/product'
import ProductCard from './ProductCard'
import { ProductTranslation } from '../lib/i18n'

const UPLOAD_TEMP_ENABLED = true // set true when /api/upload/temp/ exists

interface Product {
  id: number
  name: string
  slug: string
  price: string | number | null
  currency?: string | null
  old_price?: string | null
  main_image_url?: string | null
  main_image?: string | null
  video_url?: string | null
  product_type?: string
  is_new?: boolean
  is_bestseller?: boolean
  is_featured?: boolean
  translations?: ProductTranslation[]
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

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !file.type.startsWith('image/')) {
      setError(t('select_image', 'Выберите изображение'))
      return
    }
    setError(null)
    setSearching(true)
    setResults([])
    try {
      if (UPLOAD_TEMP_ENABLED) {
        const formData = new FormData()
        formData.append('file', file)
        const uploadRes = await api.post('/upload/temp/', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        const imageUrl = uploadRes.data?.url || uploadRes.data?.image_url
        if (!imageUrl) {
          setError(t('upload_failed', 'Не удалось загрузить изображение. Используйте URL.'))
          return
        }
        await handleUrlSearch(imageUrl)
      } else {
        setError(t('upload_unavailable', 'Загрузка файла недоступна. Вставьте URL изображения ниже.'))
      }
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        || (err as Error)?.message
        || t('search_error', 'Ошибка поиска')
      setError(String(msg))
      setResults([])
    } finally {
      setSearching(false)
    }
  }

  const handleUrlSearch = async (url: string) => {
    if (!url.trim()) return
    setError(null)
    setSearching(true)
    setResults([])
    try {
      const searchRes = await api.post('/recommendations/search_by_image/', {
        image_url: url.trim(),
        limit: 12,
      })
      const foundResults = searchRes.data.results || []
      setResults(foundResults)
      if (foundResults.length === 0) {
        setError(t('products_not_found', 'Товары не найдены'))
      }
    } catch (err: unknown) {
      const errorData = (err as { response?: { data?: { error?: string } } })?.response?.data
      if (errorData?.error === "invalid_image_url") {
        setError(t('invalid_image_url', 'Не удалось обработать URL. Убедитесь, что ссылка ведет на картинку (.jpg, .png), а не на веб-страницу.'))
      } else {
        const msg = errorData?.error || (err as Error)?.message || t('search_error', 'Ошибка поиска')
        setError(String(msg))
      }
      setResults([])
    } finally {
      setSearching(false)
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
          accept="image/*"
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
              key={r.product_id}
              id={r.product.id}
              baseProductId={(r.product as { base_product_id?: number }).base_product_id}
              name={r.product.name}
              slug={r.product.slug}
              price={r.product.price != null ? String(r.product.price) : null}
              currency={r.product.currency || 'RUB'}
              oldPrice={r.product.old_price != null ? String(r.product.old_price) : null}
              imageUrl={r.product.main_image_url || r.product.main_image}
              videoUrl={r.product.video_url}
              hasManualMainImage={(r.product as any).has_manual_main_image}
              productType={r.product.product_type || 'medicines'}
              isBaseProduct={isBaseProductType(r.product.product_type || 'medicines')}
              isBestseller={r.product.is_bestseller}
              isNew={r.product.is_new}
              isFeatured={r.product.is_featured}
              translations={r.product.translations}
              locale={i18n.language}
            />
          ))}
        </div>
      )}
    </div>
  )
}
