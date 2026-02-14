/********
 * Конфигурация Next.js с i18n и прокси API
 */

/** @type {import('next').NextConfig} */
const { i18n } = require('./next-i18next.config')
const nextConfig = {
  reactStrictMode: true,
  i18n,
  // Оптимизация производительности
  swcMinify: true,
  compiler: {
    removeConsole: process.env.NODE_ENV === 'production',
  },
  async rewrites() {
    // Docker: INTERNAL_API_BASE=http://backend:8000. Локально с ngrok: INTERNAL_API_BASE=http://localhost:8000
    const apiDest = process.env.INTERNAL_API_BASE || 'http://backend:8000';
    const apiBase = apiDest.replace(/\/$/, '');
    return [
      {
        source: '/favicon.ico',
        destination: '/telegram-icon.png',
      },
      {
        source: '/api/:path*',
        destination: `${apiBase}/api/:path*`,
      },
      {
        source: '/backend/:path*',
        destination: `${apiBase}/api/:path*`,
      },
      // Медиа (изображения товаров): ngrok туннелирует только 3001, порт 8000 недоступен
      {
        source: '/media/:path*',
        destination: `${apiBase}/media/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
