'use client'

import { useTranslation } from 'next-i18next'
import { isVideoUrl, resolveMediaUrl, getVideoEmbedUrl } from '../lib/media'
import { ServicePortfolioItem } from './ServicePortfolioGallery'

interface ServicePortfolioStaticListProps {
  items: ServicePortfolioItem[]
}

export default function ServicePortfolioStaticList({ items }: ServicePortfolioStaticListProps) {
  const { t } = useTranslation('common')

  if (!items || items.length === 0) return null

  return (
    <div className="mx-auto max-w-7xl px-3 sm:px-6 lg:px-8 py-10">
      <div className="space-y-16">
        {items.map((item) => {
          const mediaList: { type: 'video' | 'image'; url: string; label?: string }[] = []
          
          if (item.media_items && item.media_items.length > 0) {
            item.media_items.forEach(m => {
              mediaList.push({
                type: m.media_type,
                url: resolveMediaUrl(m.media_url),
                label: m.badge !== 'none' ? m.badge : undefined
              })
            })
          } else {
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

          return (
            <div key={item.id} className="flex flex-col gap-8">
              {/* Text content - clean, no "card" style */}
              <div className="max-w-3xl">
                <div className="flex items-center gap-3 mb-2">
                  <span className="h-px w-8 bg-[var(--accent)]"></span>
                  <p className="text-xs font-bold uppercase tracking-widest text-[var(--accent)]">
                    {item.city || t('service_case', 'Кейс')}
                  </p>
                </div>
                <h3 className="text-2xl font-bold text-[var(--text-strong)] mb-3">
                  {item.title}
                </h3>
                {item.result_summary && (
                  <p className="text-sm font-medium text-main/70 mb-4 bg-[var(--accent-soft)] inline-block px-3 py-1 rounded-full">
                    {item.result_summary}
                  </p>
                )}
                {item.description && (
                  <p className="text-base text-main leading-relaxed">
                    {item.description}
                  </p>
                )}
              </div>

              {/* Media grid - static display */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {mediaList.map((media, idx) => (
                  <div 
                    key={idx} 
                    className={`relative overflow-hidden rounded-2xl bg-[var(--surface-soft)] aspect-[9/16] ${mediaList.length === 1 ? 'md:col-span-2 md:aspect-[3/2]' : 'md:aspect-[4/5]'}`}
                  >
                    {media.type === 'video' ? (
                      getVideoEmbedUrl(media.url, 'player') ? (
                        <iframe
                          src={getVideoEmbedUrl(media.url, 'player') as string}
                          className="h-full w-full object-cover"
                          allow="autoplay; fullscreen; picture-in-picture"
                          allowFullScreen
                          title={item.title}
                        />
                      ) : (
                        <video 
                          src={media.url} 
                          className="h-full w-full object-cover"
                          controls
                          playsInline
                          preload="metadata"
                          muted
                        />
                      )
                    ) : (
                      <>
                        {media.label === 'before' && (
                          <span className="absolute left-4 top-4 z-10 rounded-full bg-black/70 px-3 py-1 text-xs font-bold uppercase tracking-widest text-white">
                            {t('service_portfolio_before', 'До')}
                          </span>
                        )}
                        {media.label === 'after' && (
                          <span className="absolute left-4 top-4 z-10 rounded-full bg-[var(--accent)] px-3 py-1 text-xs font-bold uppercase tracking-widest text-white">
                            {t('service_portfolio_after', 'После')}
                          </span>
                        )}
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img 
                          src={media.url} 
                          alt={item.alt_text || item.title} 
                          className="h-full w-full object-cover"
                          loading="lazy"
                        />
                      </>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
