import { useEffect, useState } from 'react'

import { wideMasonryColumns } from '../lib/pageWidth'

/**
 * Число колонок кладки на десктопе. Сервер и ноутбук — три, как раньше; на большом
 * мониторе колонок больше, и узнаём мы это только в браузере: react-masonry-css
 * понимает лишь правила «не шире N», а его значение по умолчанию уходит в HTML с сервера.
 */
export function useWideMasonryColumns(): number {
  const [columns, setColumns] = useState(3)

  useEffect(() => {
    const update = () => setColumns(wideMasonryColumns(window.innerWidth))
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [])

  return columns
}
