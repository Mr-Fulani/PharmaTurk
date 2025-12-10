import Head from 'next/head'
import axios from 'axios'
import Link from 'next/link'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import BannerCarousel from '../../components/BannerCarouselMedia'

interface Category {
  id: number
  name: string
  slug: string
  description?: string
  products_count?: number
  parent?: number | null
  card_media_url?: string | null
}

export default function CategoriesPage({ categories }: { categories: Category[] }) {
  const { t } = useTranslation('common')

  // Такая же функция, как на главной, чтобы не было расхождений при перезагрузке
  const resolveMediaUrl = (url?: string | null) => {
    if (!url) return ''

    // Абсолютный URL, но мог прийти с хостом backend:8000 — переписываем на публичный
    const clientApi = process.env.NEXT_PUBLIC_API_BASE
    const serverApi = process.env.INTERNAL_API_BASE

    const stripApiSuffix = (value?: string) => {
      if (!value) return ''
      return value.endsWith('/api') ? value.slice(0, -4) : value
    }

    const fallbackMediaBase =
      process.env.NEXT_PUBLIC_MEDIA_BASE ||
      'http://localhost:8000'

    const replaceBackendHost = (base: string) => {
      if (!base) return ''
      try {
        const u = new URL(base)
        if (u.hostname === 'backend') {
          if (typeof window !== 'undefined') {
            u.hostname = window.location.hostname
          } else {
            u.hostname = 'localhost'
            u.port = u.port || '8000'
          }
        }
        return u.toString().replace(/\/$/, '')
      } catch {
        return base
      }
    }

    const serverMediaBase = replaceBackendHost(stripApiSuffix(serverApi) || 'http://backend:8000')
    const clientMediaBase =
      typeof window === 'undefined'
        ? replaceBackendHost(stripApiSuffix(serverApi) || stripApiSuffix(clientApi) || fallbackMediaBase)
        : replaceBackendHost(stripApiSuffix(clientApi) || '') ||
          `${window.location.protocol}//${window.location.hostname}:8000`

    // Если абсолютный и указывает на backend/внутренний хост — заменяем на публичный
    if (/^https?:\/\//i.test(url)) {
      try {
        const u = new URL(url)
        if (serverMediaBase && url.startsWith(serverMediaBase)) {
          return url.replace(serverMediaBase, clientMediaBase || u.origin)
        }
        // если хост "backend" или "backend:8000", заменим на доступный
        if (u.hostname === 'backend') {
          const origin8000 =
            typeof window !== 'undefined'
              ? `${window.location.protocol}//${window.location.hostname}:8000`
              : fallbackMediaBase
          return `${origin8000}${u.pathname}${u.search}`
        }
        return url
      } catch {
        return url
      }
    }

    // Относительный путь
    if (clientMediaBase) {
      return url.startsWith('/') ? `${clientMediaBase}${url}` : `${clientMediaBase}/${url}`
    }

    if (typeof window !== 'undefined') {
      const origin = window.location.origin
      return url.startsWith('/') ? `${origin}${url}` : `${origin}/${url}`
    }
    return url
  }

  const extractYouTubeId = (url?: string | null) => {
    if (!url) return null
    const match =
      url.match(/(?:youtube\.com\/(?:[^/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/|m\.youtube\.com\/watch\?v=)([^"&?/\\s]{11})/) ||
      url.match(/(?:youtube\.com\/shorts\/|m\.youtube\.com\/shorts\/)([^"&?/\\s]+)/)
    return match && match[1] ? match[1] : null
  }

  const getYouTubeThumbnail = (url?: string | null) => {
    const youtubeId = extractYouTubeId(url)
    return youtubeId ? `https://img.youtube.com/vi/${youtubeId}/hqdefault.jpg` : null
  }

  const renderMedia = (mediaUrl?: string | null, alt?: string) => {
    if (!mediaUrl) return null

    const youtubeId = extractYouTubeId(mediaUrl)
    if (youtubeId) {
      const youtubeThumb = getYouTubeThumbnail(mediaUrl)
      const base = `https://www.youtube-nocookie.com/embed/${youtubeId}`
      const params = [
        'autoplay=1',
        'mute=1',
        'loop=1',
        `playlist=${youtubeId}`,
        'controls=0',
        'playsinline=1',
        'rel=0',
        'modestbranding=1',
        'iv_load_policy=3',
        'cc_load_policy=0',
        'fs=0',
        'disablekb=1',
        'showinfo=0',
        'autohide=1',
      ].join('&')
      const embedUrl = `${base}?${params}`
      return (
        <div className="absolute inset-0 h-full w-full overflow-hidden">
          {youtubeThumb && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={youtubeThumb}
              alt={alt || ''}
              className="absolute inset-0 h-full w-full object-cover"
            />
          )}
          <iframe
            src={embedUrl}
            title={alt || 'YouTube'}
            className="absolute inset-0 h-full w-full object-cover"
            allow="autoplay; encrypted-media; picture-in-picture"
            loading="lazy"
            style={{ opacity: 0, transition: 'opacity 0.4s ease' }}
            onLoad={(e) => {
              const el = e.currentTarget
              setTimeout(() => {
                el.style.opacity = '1'
              }, 3000) // скрываем стартовые оверлеи YouTube
            }}
            allowFullScreen={false}
          />
        </div>
      )
    }

    // Обычная обработка файла/изображения
    const src = resolveMediaUrl(mediaUrl)
    if (!src) return null

    const normalized = src.split('?')[0].toLowerCase()
    const isVideo = /\.(mp4|mov|webm|m4v)$/i.test(normalized)

    if (isVideo) {
      return (
        <video
          className="absolute inset-0 h-full w-full object-cover"
          autoPlay
          muted
          loop
          playsInline
        >
          <source src={src} />
        </video>
      )
    }

    return (
      <img
        src={src}
        alt={alt || ''}
        className="absolute inset-0 h-full w-full object-cover"
      />
    )
  }

  return (
    <>
      <Head>
        <title>{t('menu_categories', 'Категории')} — Turk-Export</title>
      </Head>
      <main className="bg-gray-50 min-h-screen">
        {/* Hero banner */}
        <section className="bg-gradient-to-r from-violet-700 to-indigo-600 text-white py-12">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col gap-4">
            <div>
              <p className="text-sm uppercase tracking-widest opacity-80">Каталог</p>
              <h1 className="text-3xl md:text-4xl font-bold mt-1">Категории товаров</h1>
              <p className="mt-2 text-lg opacity-90">
                Выберите основную категорию — карточки и баннеры как на главной.
              </p>
            </div>
          </div>
        </section>

        {/* Main banner from CMS */}
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 mt-8 mb-8">
          <BannerCarousel position="main" />
              </div>

        {/* Cards grid */}
        <section className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 pb-12">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {categories.map((c) => {
              return (
                <Link
                  key={c.id}
                  href={`/categories/${c.slug}`}
                  className="relative h-44 rounded-xl overflow-hidden block transform hover:scale-[1.02] transition-transform duration-300 shadow-md hover:shadow-xl bg-gray-900/10"
                >
                  {renderMedia(c.card_media_url, c.name)}
                  <div className="absolute inset-0 bg-black/35" />
                  <div className="absolute inset-0 flex items-center justify-center p-4 z-10">
                    <div className="text-center text-white drop-shadow">
                      <h3 className="text-xl font-bold mb-1">{c.name}</h3>
              {c.description ? (
                        <p className="text-sm opacity-90 line-clamp-2">{c.description}</p>
                      ) : null}
                      {c.products_count ? (
                        <p className="text-xs opacity-80 mt-2">{c.products_count} товаров</p>
              ) : null}
                    </div>
                  </div>
            </Link>
              )
            })}
        </div>
        </section>
      </main>
    </>
  )
}

export async function getServerSideProps(ctx: any) {
  try {
    const base = process.env.INTERNAL_API_BASE || 'http://backend:8000'

    // Берём только корневые с бэкенда (top_level), чтобы не тянуть весь список
    const res = await axios.get(`${base}/api/catalog/categories`, {
      params: { top_level: true, page_size: 200 }
    })
    const all: Category[] = Array.isArray(res.data) ? res.data : (res.data.results || [])

    // Нормализуем слуги (underscores -> dash) и устраняем дубли
    const uniqueMap = new Map<string, Category>()
    all.forEach((c) => {
      const normSlug = (c.slug || '').replace(/_/g, '-')
      if (!uniqueMap.has(normSlug)) {
        uniqueMap.set(normSlug, { ...c, slug: normSlug })
      }
    })

    const categories = Array.from(uniqueMap.values())
      .sort((a, b) => {
        const sa = (a as any).sort_order ?? 0
        const sb = (b as any).sort_order ?? 0
        return sa - sb
      })

    return { props: { ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])), categories } }
  } catch (e) {
    return { props: { ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])), categories: [] } }
  }
}
