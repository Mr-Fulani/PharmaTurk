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
  images: {
    formats: ['image/avif', 'image/webp'],
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'i.pinimg.com',
      },
      {
        protocol: 'https',
        hostname: 'fastly.picsum.photos',
      },
      {
        protocol: 'https',
        hostname: 'picsum.photos',
      },
      {
        protocol: 'https',
        hostname: 'img.youtube.com',
      }
    ],
  },
  async headers() {
    return [
      {
        source: '/fonts/:path*',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=31536000, immutable',
          },
        ],
      },
      {
        source: '/:path*.{png,jpg,jpeg,svg,webp,ico}',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=31536000, stale-while-revalidate=59',
          },
        ],
      },
    ];
  },
  async rewrites() {
    // Docker: INTERNAL_API_BASE=http://backend:8000. Локально с ngrok: INTERNAL_API_BASE=http://localhost:8000
    const apiDest = process.env.INTERNAL_API_BASE || 'http://backend:8000';
    const apiBase = apiDest.replace(/\/$/, '');
    return [
      {
        source: '/favicon.ico',
        destination: '/favicon.ico', // Update when you have a real favicon for Mudaroba
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
