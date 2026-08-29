import type { ProductTranslation } from '../lib/i18n'

export type MoneyValue = string | number

export type CartVerificationStatus =
  | 'not_checked'
  | 'pending_confirmation'
  | 'verified'
  | 'blocked'
  | 'retryable_error'
  | 'unsupported'

export type CartVerificationIssueCode =
  | 'supplier_confirmation_required'
  | 'source_out_of_stock'
  | 'source_quantity_changed'
  | 'source_price_changed'
  | 'source_unreachable'
  | 'verification_unsupported'
  | 'cart_changed'

export type CartStockPrecision = 'exact' | 'boolean' | 'unknown'
export type CartPriceChangeState = 'none' | 'decreased' | 'increased'

export interface CartIssue {
  code: CartVerificationIssueCode
  message?: string
  blocking: boolean
  item_id?: number
}

export interface CartItem {
  id: number
  product: number
  product_name?: string
  product_translations?: ProductTranslation[]
  product_slug?: string
  product_variant_slug?: string
  product_parent_slug?: string
  product_type?: string
  product_image_url?: string
  product_video_url?: string | null
  chosen_size?: string
  quantity: number
  price: MoneyValue
  currency: string
  old_price?: MoneyValue | null
  old_price_formatted?: string | null
  source_offer?: number | null
  verification_status?: CartVerificationStatus
  source_checked_at?: string | null
  source_availability_status?: string
  observed_source_price?: MoneyValue | null
  observed_source_currency?: string
  observed_public_price?: MoneyValue | null
  observed_public_currency?: string
  observed_stock_precision?: CartStockPrecision
  observed_stock_quantity?: number | null
  verified_quantity?: number | null
  verification_issues?: CartVerificationIssueCode[]
  price_change_state?: CartPriceChangeState
  price_acknowledged_at?: string | null
  price_acknowledged_value?: MoneyValue | null
  price_acknowledged_currency?: string
  issues?: CartIssue[]
  is_payable?: boolean
}

export interface PromoCode {
  id: number
  code: string
  discount_type?: string
  discount_value: MoneyValue
  description?: string
}

export interface Cart {
  id: number | null
  items: CartItem[]
  items_count: number
  payable_items_count?: number
  issues?: CartIssue[]
  has_blocking_issues?: boolean
  total_amount: MoneyValue
  discount_amount?: MoneyValue
  final_amount?: MoneyValue
  currency?: string
  promo_code?: PromoCode | null
  shipping_options?: { air: number; sea: number; ground: number }
  shipping_requires_quote?: boolean
  free_shipping_threshold?: number | null
  created_at?: string
  updated_at?: string
  operation_issues?: CartIssue[]
}

export interface CartVerificationSnapshot {
  status?: CartVerificationStatus
  availability_status?: string
  stock_precision?: CartStockPrecision
  available_quantity?: number | null
  source_price?: MoneyValue | null
  source_currency?: string
  public_price?: MoneyValue | null
  public_currency?: string
  checked_at?: string
}

export interface CartVerificationErrorPayload {
  detail?: string
  code?: CartVerificationIssueCode
  issues?: CartIssue[]
  verification?: CartVerificationSnapshot
}
