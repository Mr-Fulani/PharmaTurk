import { useState } from 'react'
import { useTranslation } from 'next-i18next'
import api from '../lib/api'
import { formatFitmentPeriod, formatFitmentPower, summarizeModels } from '../lib/autoPartFitment'

export interface AutoPartNumber {
  number: string
  kind: 'oem' | 'cross' | string
  maker?: string | null
}

export interface AutoPartFitmentSummary {
  count: number
  makes: { slug: string; name: string; count: number; models: string[] }[]
}

interface FitmentRow {
  model: string
  generation: string
  engine: string
  power_kw: number | null
  power_hp: number | null
  year_from: number | null
  month_from: number | null
  year_to: number | null
  month_to: number | null
  note: string
}

interface Props {
  productSlug: string
  partNumber?: string | null
  numbers?: AutoPartNumber[] | null
  summary?: AutoPartFitmentSummary | null
}

type MakeState = { status: 'loading' | 'ready' | 'error'; rows: FitmentRow[] }

/**
 * Карточка автозапчасти: OEM-номера и аналоги, список автомобилей, к которым подходит деталь.
 * Марки с моделями приходят вместе со страницей; строки марки (кузов, двигатель, годы — их
 * бывает сотни) подгружаются, когда покупатель открывает марку.
 */
export default function AutoPartFitment({ productSlug, partNumber, numbers, summary }: Props) {
  const { t, i18n } = useTranslation('common')
  const locale = i18n.language === 'en' ? 'en' : 'ru'
  const [makes, setMakes] = useState<Record<string, MakeState>>({})
  const oem = (numbers || []).filter((row) => row.kind !== 'cross')
  const cross = (numbers || []).filter((row) => row.kind === 'cross')
  const fitmentMakes = summary?.makes || []

  if (!partNumber && oem.length === 0 && cross.length === 0 && fitmentMakes.length === 0) return null

  const loadMake = (slug: string) => {
    if (makes[slug]?.status === 'ready' || makes[slug]?.status === 'loading') return
    setMakes((current) => ({ ...current, [slug]: { status: 'loading', rows: [] } }))
    api
      .get(`/catalog/auto-parts/products/${encodeURIComponent(productSlug)}/fitments`, {
        params: { make: slug, page_size: 500 },
      })
      .then((response) => {
        const rows = Array.isArray(response.data?.results) ? response.data.results : []
        setMakes((current) => ({ ...current, [slug]: { status: 'ready', rows } }))
      })
      .catch(() => setMakes((current) => ({ ...current, [slug]: { status: 'error', rows: [] } })))
  }

  const numberList = (rows: AutoPartNumber[]) => (
    <ul className="flex flex-wrap gap-2">
      {rows.map((row) => (
        <li
          key={`${row.kind}-${row.number}`}
          className="rounded-lg border border-[var(--border)] bg-[var(--card-bg)] px-3 py-2 text-sm"
        >
          <span className="font-semibold text-main">{row.number}</span>
          {row.maker && <span className="ml-2 text-[var(--text-weak)]">{row.maker}</span>}
        </li>
      ))}
    </ul>
  )

  return (
    <section className="mt-10" data-analytics-placement="auto_part_fitment">
      {(partNumber || oem.length > 0 || cross.length > 0) && (
        <div className="mb-8">
          <h2 className="mb-3 text-xl font-bold text-main">{t('auto_part_numbers_title', 'Номера детали')}</h2>
          {partNumber && (
            <p className="mb-3 text-sm text-main">
              {t('auto_part_number_label', 'Артикул производителя')}: <span className="font-semibold">{partNumber}</span>
            </p>
          )}
          {oem.length > 0 && (
            <div className="mb-3">
              <h3 className="mb-2 text-sm font-semibold text-[var(--text-weak)]">
                {t('auto_part_oem_title', 'Оригинальные номера (OEM)')}
              </h3>
              {numberList(oem)}
            </div>
          )}
          {cross.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-semibold text-[var(--text-weak)]">
                {t('auto_part_cross_title', 'Номера-аналоги')}
              </h3>
              {numberList(cross)}
            </div>
          )}
        </div>
      )}

      {fitmentMakes.length > 0 && (
        <div>
          <h2 className="mb-1 text-xl font-bold text-main">{t('auto_part_fitment_title', 'Подходит к автомобилям')}</h2>
          <p className="mb-4 text-sm text-[var(--text-weak)]">
            {t('auto_part_fitment_hint', {
              count: summary?.count || 0,
              defaultValue:
                'Вариантов кузова и двигателя: {{count}}. Перед заказом сверьте деталь по OEM-номеру или по VIN автомобиля.',
            })}
          </p>
          <div className="flex flex-col gap-2">
            {fitmentMakes.map((make) => {
              const state = makes[make.slug]
              return (
                <details
                  key={make.slug}
                  className="rounded-[var(--card-radius)] border border-[var(--border)] bg-[var(--card-bg)]"
                  onToggle={(event) => {
                    if ((event.currentTarget as HTMLDetailsElement).open) loadMake(make.slug)
                  }}
                >
                  <summary className="flex min-h-[44px] cursor-pointer flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2">
                    <span className="font-semibold text-main">{make.name}</span>
                    <span className="text-sm text-[var(--text-weak)]">{summarizeModels(make.models, 6, locale)}</span>
                    <span className="ml-auto text-sm text-[var(--text-weak)]">{make.count}</span>
                  </summary>
                  <div className="border-t border-[var(--border)] px-4 py-3">
                    {(!state || state.status === 'loading') && (
                      <p className="text-sm text-[var(--text-weak)]">{t('loading', 'Загрузка...')}</p>
                    )}
                    {state?.status === 'error' && (
                      <button
                        type="button"
                        className="min-h-[44px] text-sm font-semibold text-[var(--accent)]"
                        onClick={() => loadMake(make.slug)}
                      >
                        {t('auto_part_fitment_retry', 'Не удалось загрузить список. Повторить')}
                      </button>
                    )}
                    {state?.status === 'ready' && (
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-sm text-main">
                          <thead className="text-[var(--text-weak)]">
                            <tr>
                              <th className="py-1 pr-3 font-medium">{t('auto_part_fitment_body', 'Модель и кузов')}</th>
                              <th className="py-1 pr-3 font-medium">{t('auto_part_fitment_engine', 'Двигатель')}</th>
                              <th className="py-1 pr-3 font-medium">{t('auto_part_fitment_power', 'Мощность')}</th>
                              <th className="py-1 font-medium">{t('auto_part_fitment_years', 'Годы выпуска')}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {state.rows.map((row, index) => (
                              <tr key={index} className="border-t border-[var(--border)] align-top">
                                <td className="py-1.5 pr-3">{row.generation || row.model}</td>
                                <td className="py-1.5 pr-3">{row.engine || row.note}</td>
                                <td className="whitespace-nowrap py-1.5 pr-3">{formatFitmentPower(row, locale)}</td>
                                <td className="whitespace-nowrap py-1.5">{formatFitmentPeriod(row, locale)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </details>
              )
            })}
          </div>
        </div>
      )}
    </section>
  )
}
