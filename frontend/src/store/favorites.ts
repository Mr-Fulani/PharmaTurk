import { create } from 'zustand'
import api, { initCartSession } from '../lib/api'

interface Favorite {
  id: number
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
    _product_type?: string
  }
  created_at: string
}

interface FavoritesStore {
  favorites: Favorite[]
  count: number
  loading: boolean
  refreshing: boolean
  refresh: (currency?: string) => Promise<void>
  add: (productId: number, productType?: string) => Promise<void>
  remove: (productId: number, productType?: string) => Promise<void>
  check: (productId: number, productType?: string) => Promise<boolean>
  isFavorite: (productId: number) => boolean
}

export const useFavoritesStore = create<FavoritesStore>((set, get) => ({
  favorites: [],
  count: 0,
  loading: false,
  refreshing: false,
  
  refresh: async (currency?: string) => {
    // Предотвращаем множественные одновременные запросы
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
  
  add: async (productId: number, productType: string = 'medicines') => {
    try {
      initCartSession()
      await api.post('/catalog/favorites/add', { product_id: productId, product_type: productType })
      await get().refresh()
    } catch (error: any) {
      const detail = error?.response?.data?.detail || error?.message || 'Ошибка добавления в избранное'
      throw new Error(detail)
    }
  },
  
  remove: async (productId: number, productType: string = 'medicines') => {
    try {
      initCartSession()
      await api.delete('/catalog/favorites/remove', { data: { product_id: productId, product_type: productType } })
      await get().refresh()
    } catch (error: any) {
      const detail = error?.response?.data?.detail || error?.message || 'Ошибка удаления из избранного'
      throw new Error(detail)
    }
  },
  
  check: async (productId: number, productType: string = 'medicines') => {
    try {
      initCartSession()
      const response = await api.get('/catalog/favorites/check', { params: { product_id: productId, product_type: productType } })
      return response.data?.is_favorite || false
    } catch (error) {
      console.error('Failed to check favorite:', error)
      return false
    }
  },
  
  isFavorite: (productId: number) => {
    const { favorites } = get()
    return favorites.some(fav => fav.product.id === productId)
  },
}))
