import Link from 'next/link'
import { useTranslation } from 'next-i18next'

interface CategoryHeroProps {
  title: string
  description?: string | null
  totalCount: number
  categorySlug?: string
  worksHref?: string | null
  eyebrow?: string
  countLabel?: string
  showWhatsapp?: boolean
}

/**
 * Адаптивный баннер для страниц категорий.
 * Отображает название, описание, количество товаров и ссылку на WhatsApp.
 */
export default function CategoryHero({
  title,
  description,
  totalCount,
  categorySlug,
  worksHref,
  eyebrow,
  countLabel,
  showWhatsapp = true,
}: CategoryHeroProps) {
  const { t } = useTranslation('common')

  const whatsappNumber = '905525821497'
  const message = t('whatsapp_banner_message', { category: title || categorySlug || '' })
  const whatsappUrl = `https://wa.me/${whatsappNumber}?text=${encodeURIComponent(message)}`

  return (
    <div className="category-hero relative isolate overflow-hidden text-white py-12 md:py-16 transition-colors duration-200">
      <img
        src="/category-hero-istanbul.png"
        alt=""
        aria-hidden="true"
        className="hero-image absolute inset-0 -z-20 h-full w-full object-cover"
      />
      <div aria-hidden="true" className="hero-vignette absolute inset-0 -z-10" />
      <div aria-hidden="true" className="hero-light absolute inset-0 -z-10">
        <span className="light-sweep" />
      </div>

      <div className="relative mx-auto max-w-7xl px-3 sm:px-6 lg:px-8">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-8">
          <div className="flex-1">
            {eyebrow ? (
              <p className="mb-3 text-sm uppercase tracking-widest text-white/80">
                {eyebrow}
              </p>
            ) : null}
            <h1 className="text-4xl md:text-5xl font-bold mb-4 uppercase leading-tight tracking-normal drop-shadow-sm">
              {title}
            </h1>
            
            {description && (
              <p className="text-lg md:text-xl opacity-90 max-w-2xl uppercase leading-relaxed mb-6">
                {description}
              </p>
            )}
            
            <div className="mt-2 flex flex-wrap items-center gap-4 text-sm opacity-90 uppercase tracking-widest">
              <span>
                {countLabel || t('products_found')}: <span suppressHydrationWarning className="font-bold border-b-2 border-white/30 ml-1">{totalCount}</span>
              </span>
            </div>
          </div>
          
          <div className="flex flex-shrink-0 flex-col gap-3 pb-1 sm:flex-row sm:items-center">
            {worksHref ? (
              <Link
                href={worksHref}
                className="inline-flex items-center justify-center gap-3 rounded-2xl bg-white px-8 py-4 text-base font-bold uppercase tracking-wider text-[var(--accent)] shadow-lg transition-all duration-300 hover:scale-105 active:scale-95"
              >
                <span>{t('service_portfolio_view_all', 'Смотреть все кейсы')}</span>
                <span aria-hidden="true">→</span>
              </Link>
            ) : null}

            {showWhatsapp ? (
              <a
                href={whatsappUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-3 px-8 py-4 bg-white/10 hover:bg-white/20 border border-white/40 rounded-2xl transition-all duration-300 group backdrop-blur-sm hover:scale-105 active:scale-95 shadow-lg"
              >
                <div className="relative">
                  <img
                    src="/whatsapp.svg"
                    alt="WhatsApp"
                    className="w-7 h-7 filter brightness-0 invert transition-transform duration-300 group-hover:rotate-12"
                  />
                  <span className="absolute -top-1 -right-1 flex h-3 w-3">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
                  </span>
                </div>
                <span className="text-base font-bold uppercase tracking-wider">
                  {t('whatsapp_banner_button_text', {
                    item: t(`whatsapp_banner_item_${categorySlug}`, {
                      defaultValue: t('whatsapp_banner_item_default', 'товар')
                    })
                  })}
                </span>
              </a>
            ) : null}
          </div>
        </div>
      </div>

      <style jsx>{`
        .category-hero {
          --hero-height: clamp(18rem, 34vw, 28rem);
          min-height: var(--hero-height);
          display: flex;
          align-items: center;
          clip-path: inset(0);
          background: #10201f;
        }

        .hero-image {
          position: fixed;
          inset: 0;
          width: 100vw;
          height: var(--hero-height);
          object-position: center 44%;
          transform: translateZ(0) scale(1.02);
          animation: heroImageDrift 18s ease-in-out infinite alternate;
        }

        .hero-vignette {
          background:
            linear-gradient(90deg, rgba(3, 13, 16, 0.86) 0%, rgba(4, 22, 24, 0.68) 40%, rgba(6, 19, 21, 0.18) 72%, rgba(6, 19, 21, 0.38) 100%),
            linear-gradient(180deg, rgba(0, 0, 0, 0.12) 0%, rgba(0, 0, 0, 0.42) 100%);
        }

        .hero-light {
          overflow: hidden;
          pointer-events: none;
        }

        .light-sweep {
          position: absolute;
          top: -18%;
          right: -8%;
          width: 42%;
          height: 138%;
          background: linear-gradient(90deg, transparent, rgba(255, 210, 132, 0.2), transparent);
          filter: blur(18px);
          opacity: 0.6;
          transform: skewX(-18deg);
          animation: lightSweep 14s ease-in-out infinite alternate;
        }

        :global(.dark) .hero-image {
          filter: saturate(1.08) brightness(0.9) contrast(1.1);
        }

        :global(.dark) .hero-vignette {
          background:
            linear-gradient(90deg, rgba(1, 8, 12, 0.92) 0%, rgba(3, 18, 22, 0.74) 42%, rgba(6, 20, 22, 0.24) 74%, rgba(2, 9, 13, 0.48) 100%),
            linear-gradient(180deg, rgba(0, 0, 0, 0.2) 0%, rgba(0, 0, 0, 0.54) 100%);
        }

        @keyframes heroImageDrift {
          from { transform: translate3d(0, 0, 0) scale(1.02); }
          to { transform: translate3d(-0.9rem, 0.35rem, 0) scale(1.055); }
        }

        @keyframes lightSweep {
          from { transform: translateX(0) skewX(-18deg); opacity: 0.38; }
          to { transform: translateX(-18%) skewX(-18deg); opacity: 0.72; }
        }

        @media (max-width: 768px) {
          .category-hero {
            --hero-height: 22rem;
            min-height: var(--hero-height);
            align-items: flex-end;
          }

          .hero-image {
            position: absolute;
            width: 100%;
            height: 100%;
            object-position: 60% center;
          }

          .hero-vignette {
            background:
              linear-gradient(90deg, rgba(3, 13, 16, 0.88) 0%, rgba(4, 22, 24, 0.74) 58%, rgba(6, 19, 21, 0.34) 100%),
              linear-gradient(180deg, rgba(0, 0, 0, 0.08) 0%, rgba(0, 0, 0, 0.52) 100%);
          }
        }

        @media (prefers-reduced-motion: reduce) {
          .hero-image,
          .light-sweep {
            animation: none;
          }
        }
      `}</style>
    </div>
  )
}
