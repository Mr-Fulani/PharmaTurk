import type {
  CartItem,
  CartVerificationErrorPayload,
  CartVerificationIssueCode,
} from '../types/cart'

const ISSUE_COPY: Record<
  CartVerificationIssueCode,
  { key: string; fallback: string }
> = {
  source_out_of_stock: {
    key: 'cart_issue_source_out_of_stock',
    fallback: 'Нет в наличии у поставщика',
  },
  source_quantity_changed: {
    key: 'cart_issue_source_quantity_changed',
    fallback: 'Доступное количество изменилось',
  },
  source_price_changed: {
    key: 'cart_issue_source_price_changed',
    fallback: 'Цена товара изменилась',
  },
  source_unreachable: {
    key: 'cart_issue_source_unreachable',
    fallback: 'Не удалось проверить поставщика. Попробуйте ещё раз.',
  },
  verification_unsupported: {
    key: 'cart_issue_verification_unsupported',
    fallback: 'Автоматическая проверка этого товара недоступна',
  },
  cart_changed: {
    key: 'cart_issue_cart_changed',
    fallback: 'Корзина изменилась во время проверки. Данные обновлены.',
  },
}

export function getCartIssueCopy(code?: string) {
  if (code && code in ISSUE_COPY) {
    return ISSUE_COPY[code as CartVerificationIssueCode]
  }
  return {
    key: 'cart_issue_default',
    fallback: 'Позиция требует проверки',
  }
}

export function getCartVerificationError(error: any): CartVerificationErrorPayload | null {
  const data = error?.response?.data
  if (!data || typeof data !== 'object') return null
  if (Array.isArray(data.operation_issues) && data.operation_issues[0]?.code) {
    return {
      detail: data.detail,
      code: data.operation_issues[0].code,
      issues: data.operation_issues,
      verification: data.verification,
    } as CartVerificationErrorPayload
  }
  if (!data.code && !Array.isArray(data.issues) && !data.verification) return null
  return data as CartVerificationErrorPayload
}

export function isBlockingCartItem(item: CartItem): boolean {
  return item.is_payable === false
}
