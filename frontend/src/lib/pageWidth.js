// Большие мониторы (замечание владельца 13.11.2026): от 1920 px страница шире —
// значения в styles/globals.css (--page-max), экран 3xl в tailwind.config.js.
// Здесь — то, что нельзя выразить одним CSS.

export const WIDE_SCREEN = 1920

/** Колонок в «кирпичной» кладке страниц «Все бренды» и «Все категории» на десктопе. */
export function wideMasonryColumns(width) {
  return width >= WIDE_SCREEN ? 4 : 3
}
