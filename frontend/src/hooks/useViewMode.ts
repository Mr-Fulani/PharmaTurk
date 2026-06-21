import { useState, useEffect, useCallback } from 'react'

export type ViewMode = 'grid' | 'list'

const STORAGE_KEY = 'catalog_view_mode'

/**
 * Режим отображения карточек каталога (сетка/список) с сохранением выбора
 * в пределах сессии (sessionStorage). Чтение происходит после монтирования,
 * чтобы избежать рассинхронизации SSR-разметки и гидрации.
 */
export function useViewMode(defaultMode: ViewMode = 'grid') {
  const [viewMode, setViewModeState] = useState<ViewMode>(defaultMode)

  useEffect(() => {
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY)
      if (saved === 'grid' || saved === 'list') {
        setViewModeState(saved)
      }
    } catch {
      // sessionStorage может быть недоступен (приватный режим и т.п.) — игнорируем
    }
  }, [])

  const setViewMode = useCallback((mode: ViewMode) => {
    setViewModeState(mode)
    try {
      sessionStorage.setItem(STORAGE_KEY, mode)
    } catch {
      // нет доступа к sessionStorage — состояние останется только в памяти
    }
  }, [])

  return [viewMode, setViewMode] as const
}
