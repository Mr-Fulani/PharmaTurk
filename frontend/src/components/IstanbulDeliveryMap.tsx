import { m, useReducedMotion } from 'framer-motion'

type MapTexts = {
  map: Record<'europe' | 'asia' | 'bosphorus' | 'marmara' | 'blackSea' | 'goldenHorn', string>
  districts: Record<string, string>
  mapLegend: Record<'pharmacy' | 'destination' | 'route', string>
}

// Схема, а не карта: берега и районы расставлены условно, чтобы было видно обе стороны города.
const DISTRICTS: Array<[key: string, x: number, y: number, side: 'eu' | 'as']> = [
  ['sariyer', 292, 82, 'eu'],
  ['sisli', 246, 196, 'eu'],
  ['besiktas', 306, 214, 'eu'],
  ['taksim', 276, 236, 'eu'],
  ['beyoglu', 300, 256, 'eu'],
  ['fatih', 236, 292, 'eu'],
  ['sultanahmet', 290, 304, 'eu'],
  ['bakirkoy', 120, 316, 'eu'],
  ['uskudar', 356, 262, 'as'],
  ['kadikoy', 352, 316, 'as'],
  ['atasehir', 432, 290, 'as'],
  ['maltepe', 474, 330, 'as'],
]
const BOSPHORUS = 'M340 34 C326 80 352 118 334 162 C318 202 344 236 322 276 L306 322'
const GOLDEN_HORN = 'M322 282 C292 270 256 256 214 244'
// Маршрут курьера: аптека в Таксиме → отель в Султанахмете (через мост над Золотым Рогом).
const ROUTE = 'M276 236 C252 262 306 278 290 304'

const waterClass = 'fill-sky-200/70 dark:fill-sky-900/40'
const waterStroke = 'stroke-sky-200/90 dark:stroke-sky-900/50'
const labelProps = {
  className: 'fill-current',
  paintOrder: 'stroke' as const,
  stroke: 'var(--surface)',
  strokeWidth: 4,
  strokeLinejoin: 'round' as const,
}

export default function IstanbulDeliveryMap({ texts }: { texts: MapTexts }) {
  const reduceMotion = useReducedMotion()

  return (
    <figure className="relative overflow-hidden rounded-3xl border border-[var(--border)] bg-[var(--surface)] p-3 shadow-sm sm:p-5">
      <svg
        viewBox="0 0 640 440"
        className="h-auto w-full text-main"
        role="img"
        aria-label={`${texts.map.europe}, ${texts.map.asia}: ${Object.values(texts.districts).join(', ')}`}
      >
        <rect width="640" height="440" rx="24" className="fill-[var(--bg)]" />
        {/* Чёрное море, Мраморное море, Босфор, Золотой Рог */}
        <path className={waterClass} d="M0 0H640V44C560 60 470 34 400 48C368 55 352 42 338 32C300 48 228 52 150 38C90 28 40 42 0 32Z" />
        <path className={waterClass} d="M0 334C80 350 160 328 230 338C270 344 288 322 306 320C330 324 362 348 430 354C520 362 580 374 640 368V440H0Z" />
        <path d={BOSPHORUS} className={waterStroke} strokeWidth="20" fill="none" strokeLinecap="round" />
        <path d={GOLDEN_HORN} className={waterStroke} strokeWidth="10" fill="none" strokeLinecap="round" />

        <g fontSize="16" fontStyle="italic" className="text-sky-700/80 dark:text-sky-300/80">
          <text x="150" y="24" {...labelProps} stroke="none">{texts.map.blackSea}</text>
          <text x="250" y="408" {...labelProps} stroke="none">{texts.map.marmara}</text>
          <text x="352" y="128" {...labelProps} stroke="none" transform="rotate(-72 352 128)">{texts.map.bosphorus}</text>
          <text x="208" y="264" fontSize="13" textAnchor="end" {...labelProps} stroke="none">{texts.map.goldenHorn}</text>
        </g>
        <g fontSize="18" fontWeight="700" className="text-main/40">
          <text x="70" y="150" {...labelProps}>{texts.map.europe}</text>
          <text x="440" y="190" {...labelProps}>{texts.map.asia}</text>
        </g>

        {/* Маршрут курьера */}
        <m.path
          d={ROUTE}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="3"
          strokeDasharray="6 6"
          strokeLinecap="round"
          initial={reduceMotion ? false : { pathLength: 0, opacity: 0 }}
          whileInView={{ pathLength: 1, opacity: 1 }}
          viewport={{ once: true, amount: 0.6 }}
          transition={{ duration: 1.6, ease: 'easeInOut', delay: 0.8 }}
        />
        {!reduceMotion && (
          <circle r="6" fill="var(--accent)" stroke="white" strokeWidth="2">
            <animateMotion dur="4s" repeatCount="indefinite" path={ROUTE} begin="2.4s" />
          </circle>
        )}

        {/* Районы */}
        {DISTRICTS.map(([key, x, y, side], index) => {
          const isPharmacy = key === 'taksim'
          const isDestination = key === 'sultanahmet'
          const accent = isPharmacy || isDestination
          return (
            <m.g
              key={key}
              initial={reduceMotion ? false : { opacity: 0, y: -10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.3 }}
              transition={{ duration: 0.4, delay: 0.05 * index }}
            >
              {!reduceMotion && accent && (
                <circle cx={x} cy={y} r="8" fill="var(--accent)" opacity="0.35">
                  <animate attributeName="r" values="8;18;8" dur="2.4s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.35;0;0.35" dur="2.4s" repeatCount="indefinite" />
                </circle>
              )}
              <circle
                cx={x}
                cy={y}
                r={accent ? 7 : 5}
                fill={accent ? 'var(--accent)' : side === 'eu' ? 'var(--text-strong)' : 'var(--accent-strong)'}
                stroke="var(--surface)"
                strokeWidth="2"
              />
              <text
                x={side === 'eu' ? x - 10 : x + 10}
                y={y + 4}
                fontSize="15"
                fontWeight={accent ? 700 : 500}
                textAnchor={side === 'eu' ? 'end' : 'start'}
                {...labelProps}
              >
                {texts.districts[key]}
              </text>
            </m.g>
          )
        })}
      </svg>
      <figcaption className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 px-1 text-xs text-main/70 sm:text-sm">
        <span className="inline-flex items-center gap-2">
          <span className="h-3 w-3 rounded-full bg-[var(--accent)]" aria-hidden="true" />
          {texts.mapLegend.pharmacy} → {texts.mapLegend.destination}
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="h-0 w-6 border-t-2 border-dashed border-[var(--accent)]" aria-hidden="true" />
          {texts.mapLegend.route}
        </span>
      </figcaption>
    </figure>
  )
}
