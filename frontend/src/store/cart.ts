import { create } from 'zustand'
import { getSingleFlight } from '../lib/api'
import type { Cart } from '../types/cart'

interface CartState {
  itemsCount: number
  payableItemsCount: number
  hasBlockingIssues: boolean
  setItemsCount: (n: number) => void
  setCartSummary: (cart: Partial<Cart>) => void
  refresh: () => Promise<void>
}

export const useCartStore = create<CartState>((set) => ({
  itemsCount: 0,
  payableItemsCount: 0,
  hasBlockingIssues: false,
  setItemsCount: (n) => {
    console.log('Cart store: setting itemsCount to', n)
    set({ itemsCount: n })
  },
  setCartSummary: (cart) => {
    const itemsCount = Number(cart.items_count ?? 0)
    const payableItemsCount = Number(cart.payable_items_count ?? itemsCount)
    set({
      itemsCount: Number.isFinite(itemsCount) ? itemsCount : 0,
      payableItemsCount: Number.isFinite(payableItemsCount) ? payableItemsCount : 0,
      hasBlockingIssues: Boolean(cart.has_blocking_issues),
    })
  },
  async refresh() {
    try {
      console.log('Cart store: refreshing cart from API')
      const r = await getSingleFlight('/orders/cart')
      const count = Number(r.data?.items_count ?? 0)
      const payableCount = Number(r.data?.payable_items_count ?? count)
      console.log('Cart store: API returned items_count =', count)
      set({
        itemsCount: Number.isFinite(count) ? count : 0,
        payableItemsCount: Number.isFinite(payableCount) ? payableCount : 0,
        hasBlockingIssues: Boolean(r.data?.has_blocking_issues),
      })
    } catch (e) {
      console.log('Cart store: refresh failed', e)
    }
  }
}))
