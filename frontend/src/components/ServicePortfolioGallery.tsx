'use client'

import { useState } from 'react'
import { useTranslation } from 'next-i18next'
import { isVideoUrl, resolveMediaUrl, getVideoEmbedUrl } from '../lib/media'

export interface ServicePortfolioMedia {
  id: number
  media_type: 'image' | 'video'
  badge: 'none' | 'before' | 'after'
  media_url: string
  sort_order: number
}

export interface ServicePortfolioItem {
  id: number
  title: string
  description?: string | null
  result_summary?: string | null
  city?: string | null
  image_url?: string | null
  before_image_url?: string | null
  after_image_url?: string | null
  video_url?: string | null
  alt_text?: string | null
  service_slug?: string | null
  service_name?: string | null
  category_slug?: string | null
  media_items?: ServicePortfolioMedia[]
}

interface ServicePortfolioGalleryProps {
  items: ServicePortfolioItem[]
  categorySlug?: string | null
  compact?: boolean
  title?: string
  description?: string
}

type MediaEntry = { type: 'video' | 'image'; url: string; label?: string }

function buildMediaList(item: ServicePortfolioItem): MediaEntry[] {
  const mediaList: { type: 'video' | 'image'; url: string; label?: string }[] = []
  
  // First add new media_items from the inline model
  if (item.media_items && item.media_items.length > 0) {
    item.media_items.forEach(m => {
      mediaList.push({
        type: m.media_type,
        url: resolveMediaUrl(m.media_url),
        label: m.badge !== 'none' ? m.badge : undefined
      })
    })
  } else {
    // Fallback for old fields
    if (item.video_url && isVideoUrl(item.video_url)) {
      mediaList.push({ type: 'video', url: resolveMediaUrl(item.video_url) })
    }
    if (item.before_image_url) {
      mediaList.push({ type: 'image', url: resolveMediaUrl(item.before_image_url), label: 'before' })
    }
    if (item.after_image_url) {
      mediaList.push({ type: 'image', url: resolveMediaUrl(item.after_image_url), label: 'after' })
    }
    if (item.image_url) {
      mediaList.push({ type: 'image', url: resolveMediaUrl(item.image_url) })
    }
  }
  return mediaList
}

function LightboxModal({
  item,
  mediaIndex,
  onClose,
  onPrevMedia,
  onNextMedia,
}: {
  item: ServicePortfolioItem
  mediaIndex: number
  onClose: () => void
  onPrevMedia: () => void
  onNextMedia: () => void
}) {
  const { t } = useTranslation('common')
  const mediaList = buildMediaList(item)
  const current = mediaList[mediaIndex]
  if (!current) return null

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-black/95 backdrop-blur-sm"
      onClick={onClose}
    >
      {/* Header */}
      <div className="flex items-start justify-between p-4 sm:p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex-1 pr-4">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-white/50 mb-1">
            {item.city || ''}
          </p>
          <h3 className="text-base sm:text-lg font-bold text-white leading-snug">{item.title}</h3>
          {item.result_summary && (
            <p className="mt-1 text-sm text-white/70">{item.result_summary}</p>
          )}
        </div>
        <button
          onClick={onClose}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/20"
          aria-label="Закрыть"
        >
          <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Main media */}
      <div className="relative flex flex-1 items-center justify-center overflow-hidden px-4" onClick={(e) => e.stopPropagation()}>
        {mediaList.length > 1 && (
          <button
            onClick={onPrevMedia}
            className="absolute left-2 z-10 flex h-10 w-10 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/20 sm:left-4"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
        )}

        <div className="relative flex h-full max-h-[60vh] w-full items-center justify-center">
          {current.type === 'video' ? (
            getVideoEmbedUrl(current.url, 'player') ? (
              <iframe
                key={current.url}
                className="max-h-full max-w-full rounded-xl object-contain w-full h-full aspect-video"
                src={getVideoEmbedUrl(current.url, 'player') as string}
                allow="autoplay; fullscreen; picture-in-picture"
                allowFullScreen
                title="Video"
              />
            ) : (
              <video
                key={current.url}
                className="max-h-full max-w-full rounded-xl object-contain"
                src={current.url}
                controls
                playsInline
                autoPlay
                muted
              />
            )

          ) : (
            <div className="relative">
              {/* Before/After badge */}
              {current.label === 'before' && (
                <span className="absolute left-3 top-3 z-10 rounded-full bg-black/70 px-3 py-1 text-xs font-bold uppercase tracking-widest text-white">
                  {t('service_portfolio_before', 'До')}
                </span>
              )}
              {current.label === 'after' && (
                <span className="absolute left-3 top-3 z-10 rounded-full bg-[var(--accent)] px-3 py-1 text-xs font-bold uppercase tracking-widest text-white">
                  {t('service_portfolio_after', 'После')}
                </span>
              )}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={current.url}
                alt={item.alt_text || item.title}
                className="max-h-[60vh] max-w-full rounded-xl object-contain"
              />
            </div>
          )}
        </div>

        {mediaList.length > 1 && (
          <button
            onClick={onNextMedia}
            className="absolute right-2 z-10 flex h-10 w-10 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/20 sm:right-4"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>
        )}
      </div>

      {/* Thumbnail strip */}
      {mediaList.length > 1 && (
        <div className="flex gap-2 overflow-x-auto p-4 sm:justify-center" onClick={(e) => e.stopPropagation()}>
          {mediaList.map((m, idx) => (
            <button
              key={idx}
              onClick={() => {/* handled via props */}}
              className={`shrink-0 h-14 w-20 overflow-hidden rounded-lg border-2 transition ${idx === mediaIndex ? 'border-[var(--accent)]' : 'border-transparent opacity-60 hover:opacity-100'}`}
            >
              {m.type === 'video' ? (
                <div className="flex h-full w-full items-center justify-center bg-white/10">
                  <svg className="h-6 w-6 text-white" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M8 5v14l11-7z" />
                  </svg>
                </div>
              ) : (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={m.url} alt="" className="h-full w-full object-cover" />
              )}
            </button>
          ))}
        </div>
      )}

      {/* Description */}
      {item.description && (
        <div className="px-4 pb-4 sm:px-6 sm:pb-6 overflow-y-auto max-h-[30vh]" onClick={(e) => e.stopPropagation()}>
          <p className="text-sm leading-6 text-white/70 whitespace-pre-line">{item.description}</p>
        </div>
      )}
    </div>
  )
}

export default function ServicePortfolioGallery({
  items,
  compact = false,
  title,
  description,
  categorySlug,
}: ServicePortfolioGalleryProps) {
  const { t } = useTranslation('common')
  const displayItems = compact ? items.slice(0, 4) : items
  const [lightbox, setLightbox] = useState<{ itemIdx: number; mediaIdx: number } | null>(null)

  if (!items.length) return null

  const openLightbox = (itemIdx: number, mediaIdx = 0) => setLightbox({ itemIdx, mediaIdx })
  const closeLightbox = () => setLightbox(null)
  const prevMedia = () => {
    if (!lightbox) return
    const mediaList = buildMediaList(items[lightbox.itemIdx])
    setLightbox({ ...lightbox, mediaIdx: (lightbox.mediaIdx - 1 + mediaList.length) % mediaList.length })
  }
  const nextMedia = () => {
    if (!lightbox) return
    const mediaList = buildMediaList(items[lightbox.itemIdx])
    setLightbox({ ...lightbox, mediaIdx: (lightbox.mediaIdx + 1) % mediaList.length })
  }

  return (
    <>
      {lightbox && (
        <LightboxModal
          item={items[lightbox.itemIdx]}
          mediaIndex={lightbox.mediaIdx}
          onClose={closeLightbox}
          onPrevMedia={prevMedia}
          onNextMedia={nextMedia}
        />
      )}

      <section className="mx-auto max-w-7xl px-3 sm:px-6 lg:px-8 pt-6 pb-2 sm:pt-8">
        <div className="rounded-[2rem] border border-[var(--border)] bg-[var(--surface)] p-5 sm:p-8 shadow-sm">
          {/* Section header */}
          {(title?.trim() || description?.trim()) && (
            <div className="mb-6 sm:mb-8">
              <p className="mb-2 text-xs font-semibold uppercase tracking-[0.25em] text-[var(--accent)]">
                {t('service_portfolio_kicker', 'Кейсы и примеры')}
              </p>
              {title?.trim() && (
                <h2 className="text-2xl font-bold tracking-tight text-[var(--text-strong)] sm:text-3xl">
                  {title}
                </h2>
              )}
              {description?.trim() && (
                <p className="mt-3 text-sm leading-6 text-main sm:text-base">
                  {description}
                </p>
              )}
            </div>
          )}

          {/* Cases grid */}
          <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
            {displayItems.map((item, itemIdx) => {
              const mediaList = buildMediaList(item)
              const primaryMedia = mediaList[0]
              const extraCount = mediaList.length - 1
              const hasBeforeAfter = !!(item.before_image_url && item.after_image_url)

              return (
                <article
                  key={item.id}
                  className="group overflow-hidden rounded-[1.5rem] border border-[var(--border)] bg-[var(--bg)] shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-lg"
                >
                  {/* Primary media */}
                  <div
                    className="relative cursor-pointer overflow-hidden bg-[var(--accent-soft)]"
                    style={{ aspectRatio: hasBeforeAfter ? '16/9' : '4/3' }}
                    onClick={() => openLightbox(itemIdx, 0)}
                  >
                    {hasBeforeAfter && !primaryMedia ? (
                      // Before/After split view (no video)
                      <div className="grid h-full w-full grid-cols-2">
                        <div className="relative overflow-hidden">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={resolveMediaUrl(item.before_image_url!)} alt={`${item.alt_text || item.title} — до`} className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105" loading="lazy" />
                          <span className="absolute left-2 top-2 rounded-full bg-black/70 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">
                            {t('service_portfolio_before', 'До')}
                          </span>
                        </div>
                        <div className="relative overflow-hidden border-l border-white/20">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={resolveMediaUrl(item.after_image_url!)} alt={`${item.alt_text || item.title} — после`} className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105" loading="lazy" />
                          <span className="absolute left-2 top-2 rounded-full bg-[var(--accent)] px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">
                            {t('service_portfolio_after', 'После')}
                          </span>
                        </div>
                      </div>
                    ) : primaryMedia?.type === 'video' ? (
                      getVideoEmbedUrl(primaryMedia.url, 'ambient') ? (
                        <iframe
                          className="h-full w-full object-cover pointer-events-none"
                          src={getVideoEmbedUrl(primaryMedia.url, 'ambient') as string}
                          allow="autoplay; fullscreen; picture-in-picture"
                          allowFullScreen
                          title="Video preview"
                        />
                      ) : (
                        <video
                          className="h-full w-full object-cover"
                          src={primaryMedia.url}
                          preload="metadata"
                          playsInline
                          autoPlay
                          loop
                          muted
                        />
                      )
                    ) : primaryMedia?.type === 'image' ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={primaryMedia.url}
                        alt={item.alt_text || item.title}
                        className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
                        loading="lazy"
                      />
                    ) : (
                      <div className="flex h-full w-full items-center justify-center text-sm text-main/50">
                        {t('service_portfolio_no_media', 'Медиа появится здесь')}
                      </div>
                    )}

                    {/* Overlay: media count badge + expand icon */}
                    <div className="absolute inset-0 flex items-end justify-between p-3 opacity-0 transition-opacity duration-300 group-hover:opacity-100 bg-gradient-to-t from-black/50 to-transparent pointer-events-none">
                      <div />
                      <div className="flex items-center gap-2">
                        {extraCount > 0 && (
                          <span className="rounded-full bg-black/70 px-2.5 py-1 text-xs font-semibold text-white">
                            +{extraCount}
                          </span>
                        )}
                        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white/20 text-white backdrop-blur-sm">
                          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                          </svg>
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Thumbnail strip for extra media */}
                  {mediaList.length > 1 && (
                    <div className="flex gap-1.5 overflow-x-auto px-3 pt-2 pb-0 scrollbar-thin">
                      {mediaList.slice(1, 5).map((m, mi) => (
                        <button
                          key={mi}
                          onClick={() => openLightbox(itemIdx, mi + 1)}
                          className="shrink-0 h-10 w-14 overflow-hidden rounded-md border border-[var(--border)] bg-[var(--accent-soft)] transition hover:opacity-80"
                        >
                          {m.type === 'video' ? (
                            <div className="flex h-full w-full items-center justify-center bg-black/20">
                              <svg className="h-4 w-4 text-[var(--accent)]" fill="currentColor" viewBox="0 0 24 24">
                                <path d="M8 5v14l11-7z" />
                              </svg>
                            </div>
                          ) : (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={m.url} alt="" className="h-full w-full object-cover" loading="lazy" />
                          )}
                        </button>
                      ))}
                      {mediaList.length > 5 && (
                        <button
                          onClick={() => openLightbox(itemIdx, 5)}
                          className="shrink-0 h-10 w-14 flex items-center justify-center rounded-md bg-[var(--accent-soft)] text-xs font-bold text-[var(--accent)] transition hover:bg-[var(--accent)] hover:text-white"
                        >
                          +{mediaList.length - 5}
                        </button>
                      )}
                    </div>
                  )}

                  {/* Text content */}
                  <div className="space-y-2 p-4">
                    {(item.city || item.result_summary) && (
                      <div className="flex flex-wrap items-center gap-1.5 text-xs uppercase tracking-[0.15em] text-main/60">
                        {item.city && <span>{item.city}</span>}
                        {item.city && item.result_summary && <span>·</span>}
                        {item.result_summary && <span>{item.result_summary}</span>}
                      </div>
                    )}
                    <h3 className="text-base font-semibold leading-snug text-[var(--text-strong)]">
                      {item.title}
                    </h3>
                    {item.description && (
                      <p className="line-clamp-3 text-sm leading-relaxed text-main">
                        {item.description}
                      </p>
                    )}
                    {mediaList.length > 0 && (
                      <button
                        onClick={() => openLightbox(itemIdx, 0)}
                        className="mt-1 inline-flex items-center gap-1.5 text-sm font-medium text-[var(--accent)] transition hover:underline"
                      >
                        {t('service_portfolio_view_case', 'Смотреть кейс')}
                        <span aria-hidden>→</span>
                      </button>
                    )}
                  </div>
                </article>
              )
            })}
          </div>

          {/* "View all" link when compact */}
          {compact && items.length > displayItems.length && categorySlug && (
            <div className="mt-6 flex justify-center sm:mt-8">
              <a
                href={`/categories/${categorySlug}/works`}
                className="inline-flex items-center gap-2 rounded-full bg-[var(--accent)] px-6 py-3 text-sm font-semibold text-white transition-transform duration-200 hover:-translate-y-0.5 hover:opacity-95"
              >
                <span>{t('service_portfolio_view_all', 'Смотреть все кейсы')}</span>
                <span aria-hidden>→</span>
              </a>
            </div>
          )}
        </div>
      </section>
    </>
  )
}
