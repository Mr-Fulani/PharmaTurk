module.exports = {
  i18n: {
    defaultLocale: 'en',
    locales: ['en', 'ru'],
    localeDetection: false, // Отключаем автоматическое определение языка для ускорения
  },
  reloadOnPrerender: process.env.NODE_ENV === 'development',
  // Оптимизация загрузки переводов
  load: 'languageOnly', // Загружаем только язык без региона (en вместо en-US)
}


