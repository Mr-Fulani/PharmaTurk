import { create } from 'zustand'
import api from '../lib/api'

interface CartState {
  itemsCount: number
  setItemsCount: (n: number) => void
  refresh: () => Promise<void>
}

export const useCartStore = create<CartState>((set) => ({
  itemsCount: 0,
  setItemsCount: (n) => {
    console.log('Cart store: setting itemsCount to', n)
    set({ itemsCount: n })
  },
  async refresh() {
    try {
      console.log('Cart store: refreshing cart from API')
      const r = await api.get('/orders/cart')
      const count = r.data?.items_count || 0
      console.log('Cart store: API returned items_count =', count)
      set({ itemsCount: count })
    } catch (e) {
      console.log('Cart store: refresh failed', e)
    }
  }
}))
