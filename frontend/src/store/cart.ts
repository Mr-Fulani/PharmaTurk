import { create } from 'zustand'
import api from '../lib/api'

interface CartState {
  itemsCount: number
  setItemsCount: (n: number) => void
  refresh: () => Promise<void>
}

export const useCartStore = create<CartState>((set) => ({
  itemsCount: 0,
  setItemsCount: (n) => set({ itemsCount: n }),
  async refresh() {
    try {
      const r = await api.get('/orders/cart/')
      set({ itemsCount: r.data?.items_count || 0 })
    } catch {}
  }
}))
