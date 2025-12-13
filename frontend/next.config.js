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
    return [
      {
        source: '/api/:path*',
        destination: 'http://backend:8000/api/:path*',
      },
      {
        source: '/backend/:path*',
        destination: 'http://backend:8000/api/:path*',
      },
    ];
  },
};

module.exports = nextConfig;
