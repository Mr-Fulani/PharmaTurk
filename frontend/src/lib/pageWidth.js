// Большие мониторы (решение владельца 13.11.2026): от 1920 px страница выглядит как на
// ноутбуке шириной 1440 px, растянутом на весь экран. Сам масштаб — свойство zoom у <html>
// в styles/globals.css; здесь — числа, по которым тест сверяет ступени.

export const BIG_SCREEN_FROM = 1920
export const LAPTOP_WIDTH = 1440
export const BIG_SCREEN_MAX_ZOOM = 2

/** Масштаб страницы для окна данной ширины: 1 до 1919 px, дальше ширина / 1440, не больше 2. */
export function bigScreenZoom(width) {
  if (width < BIG_SCREEN_FROM) return 1
  return Math.min(BIG_SCREEN_MAX_ZOOM, Math.round((width / LAPTOP_WIDTH) * 10000) / 10000)
}

/**
 * Текущий масштаб страницы (zoom у <html>), 1 — без масштаба. Координаты окна
 * (innerWidth, clientX, getBoundingClientRect) браузер отдаёт в настоящих пикселях экрана,
 * а left/top у элементов страницы задаются в увеличенных: всё, что переносит одно в другое,
 * делит на этот масштаб.
 */
export function pageZoom() {
  if (typeof window === 'undefined') return 1
  const zoom = Number(window.getComputedStyle(document.documentElement).zoom)
  return zoom > 0 ? zoom : 1
}
