import { useEffect, useRef } from 'react'
import { gtmViewItemList, type GtmEcommerceItem } from '../lib/gtm'

/**
 * view_item_list при показе списка товаров (категория, бренд) и после смены страницы/фильтров.
 * Повторная загрузка тех же товаров (SSR → клиентский запрос) событие не дублирует.
 */
export function useViewItemList(list: { id: string; name: string }, items: GtmEcommerceItem[]): void {
  const lastKeyRef = useRef('')
  const key = `${list.id}|${items.map((item) => item.item_id).join(',')}`
  useEffect(() => {
    if (!items.length || key === lastKeyRef.current) return
    lastKeyRef.current = key
    gtmViewItemList(list, items)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
}
