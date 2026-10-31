/********
 * Конфигурация Next.js с i18n и прокси API
 */

/** @type {import('next').NextConfig} */
const { i18n } = require('./next-i18next.config')

// CSP пока только Report-Only (TD-018, TD-033): браузер ничего не блокирует, нарушения
// пишет в консоль и шлёт на /api/csp-report/ (лог backend «csp»). Переход в
// enforce — отдельным шагом по docs/SECURITY_CSP.md. Политика здесь, а не в
// отдельном файле: production-образ копирует только next.config.js.
const buildCsp = ({ scriptExtra = '' } = {}) => [
  "default-src 'self'",
  // 'unsafe-inline': инлайн-скрипты Consent Mode, gtag, Метрики. Убрать — через nonce.
  `script-src 'self' 'unsafe-inline'${scriptExtra} https://www.googletagmanager.com https://*.google-analytics.com` +
    ' https://mc.yandex.ru https://mc.yandex.com https://yastatic.net https://telegram.org' +
    ' https://accounts.google.com https://www.youtube.com https://static.cloudflareinsights.com' +
    ' https://challenges.cloudflare.com',
  // www.gstatic.com — стили встроенного в браузер Google-переводчика страницы.
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://accounts.google.com https://www.gstatic.com",
  // Картинки товаров приходят с многих доменов источников — https: целиком.
  "img-src 'self' data: blob: https:",
  "font-src 'self' data: https://fonts.gstatic.com",
  "media-src 'self' blob: https://cdn.mudaroba.com",
  "connect-src 'self' https://cdn.mudaroba.com https://*.google-analytics.com https://*.analytics.google.com" +
    ' https://*.googletagmanager.com https://*.g.doubleclick.net https://www.google.com' +
    ' https://mc.yandex.ru https://mc.yandex.com https://accounts.google.com https://cloudflareinsights.com' +
    // VK ID (@vkid/sdk на /auth): конфиг, статистика и окно входа.
    ' https://id.vk.ru https://id.vk.com',
  'frame-src https://www.youtube.com https://www.youtube-nocookie.com https://player.vimeo.com' +
    ' https://oauth.telegram.org https://accounts.google.com https://challenges.cloudflare.com' +
    ' https://www.googletagmanager.com https://id.vk.ru https://id.vk.com' +
    ' https://mc.yandex.ru https://mc.yandex.com',
  "worker-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self' https://oauth.telegram.org",
  "frame-ancestors 'none'",
  'report-uri /api/csp-report/',
].join('; ')

// В dev Next нужен eval и HMR-сокеты — политика только для production-сборки.
const securityHeaders = process.env.NODE_ENV === 'production'
  ? [{ key: 'Content-Security-Policy-Report-Only', value: buildCsp() }]
  : []
// Виджет Telegram на /auth выполняет data-onauth через eval. Правило идёт после общего
// и заменяет заголовок только на страницах входа.
const authSecurityHeaders = process.env.NODE_ENV === 'production'
  ? [{ key: 'Content-Security-Policy-Report-Only', value: buildCsp({ scriptExtra: " 'unsafe-eval'" }) }]
  : []
const nextConfig = {
  reactStrictMode: true,
  i18n,
  // Таймаут прокси rewrites → backend (длинные ответы proxy-media / видео). В мс; в проде за фронтом обычно nginx.
  experimental: {
    proxyTimeout: Number(process.env.NEXT_PROXY_TIMEOUT_MS || 180000),
  },
  // Оптимизация производительности
  compiler: {
    removeConsole: process.env.NODE_ENV === 'production',
  },
  images: {
    formats: ['image/avif', 'image/webp'],
    // Без 2048/3840 по умолчанию: картинки (баннеры — 1672 px) не шире 1920,
    // Next их не увеличивает, а лишние ширины — те же байты и лишние прогоны оптимизатора.
    deviceSizes: [640, 750, 828, 1080, 1200, 1920],
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'i.pinimg.com',
      },
      {
        protocol: 'https',
        hostname: 'static.street-beat.ru',
      },
      {
        protocol: 'https',
        hostname: 'img.youtube.com',
      },
      {
        protocol: 'https',
        hostname: 'cdn.mudaroba.com',
      }
    ],
  },
  async headers() {
    return [
      ...(securityHeaders.length ? [{ source: '/:path*', headers: securityHeaders }] : []),
      ...(authSecurityHeaders.length ? [{ source: '/auth/:path*', headers: authSecurityHeaders }] : []),
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
  async redirects() {
    return [
      // Старая страница-сирота без <Head>; locale-вариант /en/bookhaven Next обрабатывает сам
      {
        source: '/bookhaven',
        destination: '/categories/books',
        statusCode: 301,
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
