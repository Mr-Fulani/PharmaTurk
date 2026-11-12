/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx}',
    './src/components/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      // Ширина страницы — общая переменная из globals.css (docs/DESIGN_THEMES.md, «Большие мониторы»).
      maxWidth: {
        page: 'var(--page-max)',
        'page-wide': 'var(--page-max-wide)',
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
