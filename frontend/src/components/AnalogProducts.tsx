import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'next-i18next'
import Link from 'next/link'
import Image from 'next/image'
import api from '../lib/api'

// ─── Типы ────────────────────────────────────────────────────────────────────

interface AnalogItem {
  id: number
  slug: string
  name: string
  brand: string | null
  /** Цена уже в display_currency (сконвертирована на бэкенде с маржой) */
  price: number | null
  old_price: number | null
  original_price: number | null
  original_currency: string
  display_currency: string
  is_available: boolean
  main_image_url: string | null
  dosage_form: string | null
  active_ingredient: string | null
  saving_percent: number | null
  saving_amount: number | null
}

interface AnalogsResponse {
  count: number
  active_ingredient: string | null
  atc_code: string | null
  display_currency: string
  results: AnalogItem[]
}

interface AnalogProductsProps {
  /** slug текущего препарата (для запроса к API) */
  medicineSlug: string
  /** Текущая цена товара (не используется напрямую — сравнение делает бэкенд) */
  currentPrice?: number | null
  /** Валюта (используется как fallback если API не вернул display_currency) */
  currency?: string
  /** Максимум аналогов для показа */
  limit?: number
}


// ─── Форматирование цены ──────────────────────────────────────────────────────

function formatPrice(price: number | null, currency: string): string {
  if (price === null || price === undefined) return '—'
  const intl = new Intl.NumberFormat('tr-TR', {
    style: 'currency',
    currency: currency || 'TRY',
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  })
  return intl.format(price)
}

// ─── Скелетон ────────────────────────────────────────────────────────────────

function AnalogSkeleton() {
  return (
    <div className="analog-skeleton">
      {[...Array(4)].map((_, i) => (
        <div key={i} className="analog-skeleton__card">
          <div className="analog-skeleton__img" />
          <div className="analog-skeleton__line analog-skeleton__line--long" />
          <div className="analog-skeleton__line analog-skeleton__line--short" />
          <div className="analog-skeleton__line analog-skeleton__line--price" />
        </div>
      ))}
    </div>
  )
}

// ─── Карточка аналога ─────────────────────────────────────────────────────────

interface AnalogCardProps {
  analog: AnalogItem
  productType: string
}

function AnalogCard({ analog, productType }: AnalogCardProps) {
  const { t } = useTranslation('common')
  const [imgError, setImgError] = useState(false)

  const href = `/${productType}/${analog.slug}`
  // Используем display_currency из API (уже сконвертировано с маржой)
  const currency = analog.display_currency || analog.original_currency || 'TRY'
  const hasSaving = analog.saving_percent !== null && analog.saving_percent > 0

  return (
    <Link href={href} className="analog-card" aria-label={analog.name}>
      {/* Бейдж экономии */}
      {hasSaving && (
        <span className="analog-card__badge">
          -{analog.saving_percent}%
        </span>
      )}

      {/* Изображение */}
      <div className="analog-card__img-wrap">
        {analog.main_image_url && !imgError ? (
          <Image
            src={analog.main_image_url}
            alt={analog.name}
            fill
            sizes="(max-width: 768px) 50vw, 200px"
            className="analog-card__img"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="analog-card__img-placeholder">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
              <path d="M9 12h6M9 16h6M7 4h10a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z" />
            </svg>
          </div>
        )}
      </div>

      {/* Контент */}
      <div className="analog-card__body">
        {analog.brand && (
          <p className="analog-card__brand">{analog.brand}</p>
        )}
        <p className="analog-card__name" title={analog.name}>{analog.name}</p>

        {analog.dosage_form && (
          <p className="analog-card__form">{analog.dosage_form}</p>
        )}

        {/* Статус наличия */}
        <span className={`analog-card__availability ${analog.is_available ? 'analog-card__availability--in' : 'analog-card__availability--out'}`}>
          {analog.is_available
            ? t('in_stock', 'В наличии')
            : t('out_of_stock', 'Нет в наличии')}
        </span>

        {/* Цена */}
        <div className="analog-card__price-block">
          {analog.price !== null ? (
            <>
              <span className="analog-card__price">
                {formatPrice(analog.price, currency)}
              </span>
              {analog.old_price && analog.old_price > analog.price && (
                <span className="analog-card__old-price">
                  {formatPrice(analog.old_price, currency)}
                </span>
              )}
            </>
          ) : (
            <span className="analog-card__price-unknown">
              {t('price_on_request', 'Цена по запросу')}
            </span>
          )}
        </div>

        {/* Выгода */}
        {hasSaving && analog.saving_amount !== null && (
          <p className="analog-card__saving">
            {t('analog_saving', { amount: formatPrice(analog.saving_amount, currency), defaultValue: `Экономия ${formatPrice(analog.saving_amount, currency)}` })}
          </p>
        )}
      </div>
    </Link>
  )
}

// ─── Главный компонент ────────────────────────────────────────────────────────

export default function AnalogProducts({
  medicineSlug,
  currentPrice,
  currency = 'TRY',
  limit = 8,
}: AnalogProductsProps) {
  const { t } = useTranslation('common')
  const [data, setData] = useState<AnalogsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const fetchAnalogs = useCallback(async () => {
    if (!medicineSlug) return
    try {
      setLoading(true)
      setError(false)
      // api.ts автоматически прокидывает X-Currency из куки — бэкенд конвертирует с маржой
      const res = await api.get<AnalogsResponse>(
        `/catalog/medicines/products/${encodeURIComponent(medicineSlug)}/analogs/`,
        { params: { limit } }
      )
      setData(res.data)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [medicineSlug, limit])

  useEffect(() => { fetchAnalogs() }, [fetchAnalogs])

  // Ничего не рендерим при ошибке или пустом результате
  if (!loading && (error || !data || data.count === 0)) return null

  return (
    <section className="analog-products" aria-labelledby="analogs-heading">
      {/* ── Заголовок блока ── */}
      <div className="analog-products__header">
        <h2 id="analogs-heading" className="analog-products__title">
          {t('analogs_title', 'Аналоги (Eşdeğerleri)')}
        </h2>
        {data?.active_ingredient && (
          <p className="analog-products__subtitle">
            {t('analog_substance', { substance: data.active_ingredient, defaultValue: `Действующее вещество: ${data.active_ingredient}` })}
          </p>
        )}
      </div>

      {/* ── Сетка карточек ── */}
      {loading ? (
        <AnalogSkeleton />
      ) : (
        <div className="analog-products__grid">
          {data!.results.map((analog) => (
            <AnalogCard
              key={analog.id}
              analog={analog}
              productType="medicines"
            />
          ))}
        </div>
      )}

      {/* ── Стили ── */}
      <style jsx>{`
        /* ── Секция ── */
        .analog-products {
          margin-top: 2.5rem;
          padding: 1.5rem;
          background: linear-gradient(135deg, rgba(var(--color-primary-rgb, 34 197 94) / 0.04) 0%, transparent 60%);
          border: 1px solid rgba(var(--color-primary-rgb, 34 197 94) / 0.15);
          border-radius: 1rem;
        }

        .analog-products__header {
          margin-bottom: 1.25rem;
        }

        .analog-products__title {
          font-size: 1.25rem;
          font-weight: 700;
          color: var(--text-strong, #111);
          margin: 0 0 0.25rem;
        }

        .analog-products__subtitle {
          font-size: 0.8125rem;
          color: var(--text-muted, #888);
          margin: 0;
        }

        /* ── Сетка ── */
        .analog-products__grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 0.875rem;
        }

        @media (min-width: 640px) {
          .analog-products__grid {
            grid-template-columns: repeat(3, 1fr);
          }
        }

        @media (min-width: 1024px) {
          .analog-products__grid {
            grid-template-columns: repeat(4, 1fr);
          }
        }

        /* ── Карточка аналога ── */
        .analog-card {
          position: relative;
          display: flex;
          flex-direction: column;
          background: var(--card-bg, #fff);
          border: 1px solid var(--border-color, #eee);
          border-radius: 0.75rem;
          overflow: hidden;
          text-decoration: none;
          color: inherit;
          transition: transform 0.2s ease, box-shadow 0.2s ease;
        }

        .analog-card:hover {
          transform: translateY(-3px);
          box-shadow: 0 8px 24px rgba(0, 0, 0, 0.1);
          border-color: var(--color-primary, #22c55e);
        }

        /* Бейдж экономии */
        .analog-card__badge {
          position: absolute;
          top: 0.5rem;
          left: 0.5rem;
          z-index: 2;
          background: #ef4444;
          color: #fff;
          font-size: 0.75rem;
          font-weight: 700;
          padding: 0.2rem 0.45rem;
          border-radius: 0.375rem;
          letter-spacing: 0.01em;
        }

        /* Изображение */
        .analog-card__img-wrap {
          position: relative;
          width: 100%;
          aspect-ratio: 1 / 1;
          background: var(--bg-subtle, #f9fafb);
        }

        .analog-card__img {
          object-fit: contain;
        }

        .analog-card__img-placeholder {
          width: 100%;
          height: 100%;
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--text-muted, #bbb);
        }

        .analog-card__img-placeholder svg {
          width: 2.5rem;
          height: 2.5rem;
        }

        /* Контент */
        .analog-card__body {
          padding: 0.625rem 0.75rem 0.75rem;
          display: flex;
          flex-direction: column;
          gap: 0.2rem;
          flex: 1;
        }

        .analog-card__brand {
          font-size: 0.7rem;
          font-weight: 600;
          color: var(--text-muted, #aaa);
          text-transform: uppercase;
          letter-spacing: 0.04em;
          margin: 0;
        }

        .analog-card__name {
          font-size: 0.8125rem;
          font-weight: 600;
          color: var(--text-strong, #111);
          margin: 0;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
          line-height: 1.35;
        }

        .analog-card__form {
          font-size: 0.7rem;
          color: var(--text-muted, #aaa);
          margin: 0;
        }

        .analog-card__availability {
          display: inline-block;
          font-size: 0.6875rem;
          font-weight: 600;
          padding: 0.15rem 0.4rem;
          border-radius: 0.3rem;
          margin-top: 0.125rem;
        }

        .analog-card__availability--in {
          background: rgba(34, 197, 94, 0.12);
          color: #16a34a;
        }

        .analog-card__availability--out {
          background: rgba(239, 68, 68, 0.1);
          color: #dc2626;
        }

        .analog-card__price-block {
          display: flex;
          align-items: baseline;
          gap: 0.4rem;
          margin-top: auto;
          padding-top: 0.375rem;
        }

        .analog-card__price {
          font-size: 1rem;
          font-weight: 700;
          color: var(--color-primary, #16a34a);
        }

        .analog-card__old-price {
          font-size: 0.75rem;
          color: var(--text-muted, #bbb);
          text-decoration: line-through;
        }

        .analog-card__price-unknown {
          font-size: 0.8125rem;
          color: var(--text-muted, #aaa);
        }

        .analog-card__saving {
          font-size: 0.7rem;
          color: #16a34a;
          font-weight: 600;
          margin: 0;
        }

        /* ── Скелетон ── */
        .analog-skeleton {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 0.875rem;
        }

        @media (min-width: 640px) {
          .analog-skeleton {
            grid-template-columns: repeat(3, 1fr);
          }
        }

        @media (min-width: 1024px) {
          .analog-skeleton {
            grid-template-columns: repeat(4, 1fr);
          }
        }

        .analog-skeleton__card {
          border-radius: 0.75rem;
          overflow: hidden;
          border: 1px solid var(--border-color, #eee);
        }

        .analog-skeleton__img {
          width: 100%;
          aspect-ratio: 1 / 1;
          background: var(--skeleton-bg, #e5e7eb);
          animation: analog-pulse 1.4s ease-in-out infinite;
        }

        .analog-skeleton__line {
          height: 0.75rem;
          margin: 0.5rem 0.75rem 0;
          border-radius: 0.375rem;
          background: var(--skeleton-bg, #e5e7eb);
          animation: analog-pulse 1.4s ease-in-out infinite;
        }

        .analog-skeleton__line--long { width: 85%; }
        .analog-skeleton__line--short { width: 55%; }
        .analog-skeleton__line--price { width: 40%; margin-bottom: 0.75rem; }

        @keyframes analog-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.45; }
        }
      `}</style>
    </section>
  )
}
