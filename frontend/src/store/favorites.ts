import { create } from 'zustand'
import api, { getSingleFlight, initCartSession } from '../lib/api'
import { ProductTranslation } from '../lib/i18n'
import { matchesFavoriteSlug } from '../lib/favoriteLinks'
import { matchesFavoriteProductIdentity } from '../lib/favoriteIdentity'
import { ProductCardGalleryImage } from '../components/ProductCardImageGallery'

export interface Favorite {
  id: number
  chosen_size?: string
  product: {
    id: number
    base_product_id?: number | null
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
    images?: ProductCardGalleryImage[] | null
    video_url?: string | null
    _product_type?: string
    translations?: ProductTranslation[]
    /** Slug цветового/мебельного варианта (shadow Product), для сопоставления с витриной */
    favorite_variant_slug?: string
    favorite_parent_slug?: string
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
  remove: (
    productId: number | undefined,
    productType?: string,
    variant?: FavoriteVariantOpts,
    favoriteId?: number
  ) => Promise<void>
  check: (productId: number | undefined, productType?: string, variant?: FavoriteVariantOpts) => Promise<boolean>
  isFavorite: (
    productId: number | undefined,
    productType?: string,
    variant?: FavoriteVariantOpts,
    productSlug?: string
  ) => boolean
}

const normType = (t: string | undefined) =>
  (t || '').toString().trim().replace(/_/g, '-').toLowerCase()

let mutationVersion = 0

const isFavoritePayload = (value: unknown): value is Favorite => {
  const row = value as Favorite | null
  return Boolean(row && Number(row.id) > 0 && row.product && typeof row.product === 'object')
}

const matchesFavorite = (
  favorite: Favorite,
  productId: number | undefined,
  productType?: string,
  variant?: FavoriteVariantOpts,
  productSlug?: string
) => {
  const type = normType(favorite.product._product_type || 'medicines')
  if (type !== normType(productType)) return false
  if (variant?.productSlug) {
    const slugOk = matchesFavoriteSlug(
      favorite.product.favorite_variant_slug,
      favorite.product.slug,
      variant.productSlug
    )
    const sizeOk = !variant.size || (favorite.product.favorite_chosen_size || '') === variant.size
    return slugOk && sizeOk
  }
  if (productId === undefined) return false
  return matchesFavoriteProductIdentity(favorite.product, productId, productSlug)
}

export const useFavoritesStore = create<FavoritesStore>((set, get) => ({
  favorites: [],
  count: 0,
  loading: false,
  refreshing: false,

  refresh: async (currency?: string) => {
    if (get().refreshing) {
      return
    }

    const startedAtMutation = mutationVersion
    set({ refreshing: true, loading: true })
    try {
      initCartSession()
      const response = await getSingleFlight('/catalog/favorites', {
        headers: currency ? { 'X-Currency': currency } : undefined,
      })
      const favorites = response.data || []
      if (startedAtMutation === mutationVersion) {
        set({ favorites, count: favorites.length, loading: false, refreshing: false })
      } else {
        set({ loading: false, refreshing: false })
      }
    } catch (error) {
      console.error('Failed to fetch favorites:', error)
      set({ loading: false, refreshing: false })
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
      let response
      if (slug) {
        response = await api.post('/catalog/favorites/add', {
          product_type: pt,
          product_slug: slug,
          size: variant?.size || '',
        })
      } else {
        if (productId === undefined || productId === null || Number(productId) <= 0) {
          throw new Error('Нужен product_id или product_slug')
        }
        response = await api.post('/catalog/favorites/add', {
          product_type: pt,
          product_id: Number(productId),
        })
      }
      if (isFavoritePayload(response.data)) {
        mutationVersion += 1
        set((state) => {
          const favorites = [
            response.data,
            ...state.favorites.filter((favorite) => favorite.id !== response.data.id),
          ]
          return { favorites, count: favorites.length }
        })
      } else {
        await get().refresh()
      }
    } catch (error: any) {
      const detail = error?.response?.data?.detail || error?.message || 'Ошибка добавления в избранное'
      throw new Error(detail)
    }
  },

  remove: async (
    productId: number | undefined,
    productType: string = 'medicines',
    variant?: FavoriteVariantOpts,
    favoriteId?: number
  ) => {
    try {
      initCartSession()
      if (favoriteId !== undefined) {
        await api.delete('/catalog/favorites/remove', {
          data: { favorite_id: favoriteId },
        })
        mutationVersion += 1
        set((state) => {
          const favorites = state.favorites.filter((favorite) => favorite.id !== favoriteId)
          return { favorites, count: favorites.length }
        })
        return
      }
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
      mutationVersion += 1
      set((state) => {
        const favorites = state.favorites.filter(
          (favorite) => !matchesFavorite(favorite, productId, pt, variant)
        )
        return { favorites, count: favorites.length }
      })
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
      const response = await getSingleFlight('/catalog/favorites/check', { params })
      return response.data?.is_favorite || false
    } catch (error) {
      console.error('Failed to check favorite:', error)
      return false
    }
  },

  isFavorite: (
    productId: number | undefined,
    productType?: string,
    variant?: FavoriteVariantOpts,
    productSlug?: string
  ) => {
    const { favorites } = get()
    return favorites.some((favorite) =>
      matchesFavorite(favorite, productId, productType, variant, productSlug)
    )
  },
}))
