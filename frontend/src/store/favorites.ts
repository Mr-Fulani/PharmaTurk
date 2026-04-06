import { create } from 'zustand'
import api, { initCartSession } from '../lib/api'
import { ProductTranslation } from '../lib/i18n'

interface Favorite {
  id: number
  chosen_size?: string
  product: {
    id: number
    name: string
    slug: string
    price: string | number | null
    currency: string | null
    active_variant_price?: string | number | null
    active_variant_currency?: string | null
    old_price?: string | number | null
    old_price_formatted?: string | null
    active_variant_old_price_formatted?: string | null
    main_image_url?: string
    video_url?: string | null
    _product_type?: string
    translations?: ProductTranslation[]
    /** Slug цветового/мебельного варианта (shadow Product), для сопоставления с витриной */
    favorite_variant_slug?: string
    favorite_chosen_size?: string
  }
  created_at: string
}

export interface FavoriteVariantOpts {
  productSlug: string
  size?: string
}

interface FavoritesStore {
  favorites: Favorite[]
  count: number
  loading: boolean
  refreshing: boolean
  refresh: (currency?: string) => Promise<void>
  add: (productId: number | undefined, productType?: string, variant?: FavoriteVariantOpts) => Promise<void>
  remove: (productId: number | undefined, productType?: string, variant?: FavoriteVariantOpts) => Promise<void>
  check: (productId: number | undefined, productType?: string, variant?: FavoriteVariantOpts) => Promise<boolean>
  isFavorite: (productId: number | undefined, productType?: string, variant?: FavoriteVariantOpts) => boolean
}

const normType = (t: string | undefined) =>
  (t || '').toString().trim().replace(/_/g, '-').toLowerCase()

export const useFavoritesStore = create<FavoritesStore>((set, get) => ({
  favorites: [],
  count: 0,
  loading: false,
  refreshing: false,

  refresh: async (currency?: string) => {
    if (get().refreshing) {
      return
    }

    set({ refreshing: true, loading: true })
    try {
      initCartSession()
      const response = await api.get('/catalog/favorites', {
        headers: currency ? { 'X-Currency': currency } : undefined,
      })
      const favorites = response.data || []
      set({ favorites, count: favorites.length, loading: false, refreshing: false })
    } catch (error) {
      console.error('Failed to fetch favorites:', error)
      set({ favorites: [], count: 0, loading: false, refreshing: false })
    }
  },

  add: async (productId: number | undefined, productType: string = 'medicines', variant?: FavoriteVariantOpts) => {
    try {
      initCartSession()
      const pt =
        productType != null && String(productType).trim() !== ''
          ? String(productType).trim()
          : 'medicines'
      const slug = variant?.productSlug?.trim()
      if (slug) {
        await api.post('/catalog/favorites/add', {
          product_type: pt,
          product_slug: slug,
          size: variant?.size || '',
        })
      } else {
        if (productId === undefined || productId === null || Number(productId) <= 0) {
          throw new Error('Нужен product_id или product_slug')
        }
        await api.post('/catalog/favorites/add', {
          product_type: pt,
          product_id: Number(productId),
        })
      }
      await get().refresh()
    } catch (error: any) {
      const detail = error?.response?.data?.detail || error?.message || 'Ошибка добавления в избранное'
      throw new Error(detail)
    }
  },

  remove: async (productId: number | undefined, productType: string = 'medicines', variant?: FavoriteVariantOpts) => {
    try {
      initCartSession()
      const pt =
        productType != null && String(productType).trim() !== ''
          ? String(productType).trim()
          : 'medicines'
      const slug = variant?.productSlug?.trim()
      if (slug) {
        await api.delete('/catalog/favorites/remove', {
          data: {
            product_type: pt,
            product_slug: slug,
            size: variant?.size || '',
          },
        })
      } else {
        if (productId === undefined || productId === null || Number(productId) <= 0) {
          throw new Error('Нужен product_id или product_slug')
        }
        await api.delete('/catalog/favorites/remove', {
          data: { product_type: pt, product_id: Number(productId) },
        })
      }
      await get().refresh()
    } catch (error: any) {
      const detail = error?.response?.data?.detail || error?.message || 'Ошибка удаления из избранного'
      throw new Error(detail)
    }
  },

  check: async (productId: number | undefined, productType: string = 'medicines', variant?: FavoriteVariantOpts) => {
    try {
      initCartSession()
      const pt =
        productType != null && String(productType).trim() !== ''
          ? String(productType).trim()
          : 'medicines'
      const slug = variant?.productSlug?.trim()
      const params: Record<string, string | number> = { product_type: pt }
      if (slug) {
        params.product_slug = slug
        if (variant?.size) params.size = variant.size
      } else {
        if (productId === undefined || productId === null || Number(productId) <= 0) return false
        params.product_id = Number(productId)
      }
      const response = await api.get('/catalog/favorites/check', { params })
      return response.data?.is_favorite || false
    } catch (error) {
      console.error('Failed to check favorite:', error)
      return false
    }
  },

  isFavorite: (productId: number | undefined, productType?: string, variant?: FavoriteVariantOpts) => {
    const { favorites } = get()
    const want = normType(productType)
    return favorites.some((fav) => {
      if (variant?.productSlug) {
        const slugOk = fav.product.favorite_variant_slug === variant.productSlug
        const sizeOk = (fav.product.favorite_chosen_size || '') === (variant.size || '')
        const typeOk = normType(fav.product._product_type || 'medicines') === want
        return slugOk && sizeOk && typeOk
      }
      if (productId === undefined) return false
      const sameId = fav.product.id === productId
      if (!productType) return sameId
      const type = normType(fav.product._product_type || 'medicines')
      return sameId && type === want
    })
  },
}))
