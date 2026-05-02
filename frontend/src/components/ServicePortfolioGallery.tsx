import Link from 'next/link'
import { useTranslation } from 'next-i18next'
import { buildProductUrl } from '../lib/urls'
import { isVideoUrl, resolveMediaUrl } from '../lib/media'

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
}

interface ServicePortfolioGalleryProps {
  items: ServicePortfolioItem[]
  categorySlug?: string | null
  compact?: boolean
  title?: string
  description?: string
}

export default function ServicePortfolioGallery({
  items,
  categorySlug,
  compact = false,
  title,
  description,
}: ServicePortfolioGalleryProps) {
  const { t } = useTranslation('common')
  const displayItems = compact ? items.slice(0, 6) : items

  if (!items.length) return null

  return (
    <section className="mx-auto max-w-7xl px-3 sm:px-6 lg:px-8 pt-6 pb-2 sm:pt-8">
      <div className="rounded-[2rem] border border-[var(--border)] bg-[var(--surface)] p-5 sm:p-8 shadow-sm">
        <div className="mb-6 flex flex-col gap-3 sm:mb-8 sm:flex-row sm:items-end sm:justify-between">
          <div className="max-w-3xl">
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.25em] text-[var(--accent)]">
              {t('service_portfolio_kicker', 'Кейсы и примеры')}
            </p>
            <h2 className="text-2xl font-bold tracking-tight text-[var(--text-strong)] sm:text-3xl">
              {title || t('service_portfolio_title', 'Примеры оказанных услуг')}
            </h2>
            <p className="mt-3 text-sm leading-6 text-main sm:text-base">
              {description || t('service_portfolio_description', 'Реальные кейсы, примеры услуг, фото, видео, документы и краткий результат по каждому проекту.')}
            </p>
          </div>
          <div className="text-sm text-main/80">
            {t('service_portfolio_count', 'Кейсов: {{count}}', { count: items.length })}
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {displayItems.map((item) => {
            const primaryVideo = item.video_url && isVideoUrl(item.video_url) ? resolveMediaUrl(item.video_url) : null
            const primaryImage = item.image_url ? resolveMediaUrl(item.image_url) : null
            const beforeImage = item.before_image_url ? resolveMediaUrl(item.before_image_url) : null
            const afterImage = item.after_image_url ? resolveMediaUrl(item.after_image_url) : null
            const serviceHref = item.service_slug ? buildProductUrl('uslugi', item.service_slug) : null
            const mediaAlt = item.alt_text || item.title
            const hasComparison = !primaryVideo && beforeImage && afterImage

            return (
              <article
                key={item.id}
                className="overflow-hidden rounded-[1.5rem] border border-[var(--border)] bg-[var(--bg)] shadow-sm transition-transform duration-200 hover:-translate-y-1"
              >
                <div className="relative aspect-[4/3] overflow-hidden bg-[var(--accent-soft)]">
                  {primaryVideo ? (
                    <video
                      className="h-full w-full object-cover"
                      src={primaryVideo}
                      controls
                      preload="metadata"
                      playsInline
                    />
                  ) : hasComparison ? (
                    <div className="grid h-full w-full grid-cols-2">
                      <div className="relative">
                        <img
                          src={beforeImage}
                          alt={`${mediaAlt} - до`}
                          className="h-full w-full object-cover"
                          loading="lazy"
                        />
                        <span className="absolute left-3 top-3 rounded-full bg-black/70 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-white">
                          {t('service_portfolio_before', 'До')}
                        </span>
                      </div>
                      <div className="relative">
                        <img
                          src={afterImage}
                          alt={`${mediaAlt} - после`}
                          className="h-full w-full object-cover"
                          loading="lazy"
                        />
                        <span className="absolute left-3 top-3 rounded-full bg-[var(--accent)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-white">
                          {t('service_portfolio_after', 'После')}
                        </span>
                      </div>
                    </div>
                  ) : primaryImage ? (
                    <img
                      src={primaryImage}
                      alt={mediaAlt}
                      className="h-full w-full object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center px-6 text-center text-sm text-main/70">
                      {t('service_portfolio_no_media', 'Медиа для кейса появится здесь')}
                    </div>
                  )}
                </div>

                <div className="space-y-3 p-5">
                  <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-[0.18em] text-main/65">
                    {item.city ? <span>{item.city}</span> : null}
                    {item.city && item.result_summary ? <span>•</span> : null}
                    {item.result_summary ? <span>{item.result_summary}</span> : null}
                  </div>

                  <h3 className="text-lg font-semibold leading-tight text-[var(--text-strong)]">
                    {item.title}
                  </h3>

                  {item.description ? (
                    <p className="line-clamp-4 text-sm leading-6 text-main">
                      {item.description}
                    </p>
                  ) : null}

                  {serviceHref && item.service_name ? (
                    <Link
                      href={serviceHref}
                      className="inline-flex items-center gap-2 text-sm font-medium text-[var(--accent)] transition-colors hover:text-[var(--accent-strong)]"
                    >
                      <span>{t('service_portfolio_related_service', 'Перейти к услуге: {{name}}', { name: item.service_name })}</span>
                      <span aria-hidden="true">→</span>
                    </Link>
                  ) : null}
                </div>
              </article>
            )
          })}
        </div>

        {compact && items.length > displayItems.length && categorySlug ? (
          <div className="mt-6 flex justify-center sm:mt-8">
            <Link
              href={`/categories/${categorySlug}/works`}
              className="inline-flex items-center gap-2 rounded-full bg-[var(--accent)] px-5 py-3 text-sm font-semibold text-white transition-transform duration-200 hover:-translate-y-0.5 hover:opacity-95"
            >
              <span>{t('service_portfolio_view_all', 'Смотреть все кейсы')}</span>
              <span aria-hidden="true">→</span>
            </Link>
          </div>
        ) : null}
      </div>
    </section>
  )
}
