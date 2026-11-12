/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx}',
    './src/components/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      // Ширина страницы — общая переменная из globals.css (docs/DESIGN_THEMES.md, «Ширина страницы»):
      // на ноутбуке прежние 72rem / 80rem, на больших мониторах — шире и одинаково для всех страниц.
      maxWidth: {
        page: 'var(--page-max)',
        'page-wide': 'var(--page-max-wide)',
      },
      // Большие мониторы: 3xl — Full HD и шире.
      screens: {
        '3xl': '1920px',
      },
    },
  },
  plugins: [],
  safelist: [
    'bg-accent',
    'bg-surface',
    'bg-page',
    'text-accent',
    'text-main',
    'border-main',
  ],
}
