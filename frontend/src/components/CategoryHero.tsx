import { useTranslation } from 'next-i18next'

interface CategoryHeroProps {
  title: string
  description?: string | null
  totalCount: number
  categorySlug?: string
}

/**
 * Адаптивный баннер для страниц категорий.
 * Отображает название, описание, количество товаров и ссылку на WhatsApp.
 */
export default function CategoryHero({ title, description, totalCount, categorySlug }: CategoryHeroProps) {
  const { t } = useTranslation('common')
  
  const whatsappNumber = '905525821497'
  const message = t('whatsapp_banner_message', { category: title || categorySlug || '' })
  const whatsappUrl = `https://wa.me/${whatsappNumber}?text=${encodeURIComponent(message)}`

  return (
    <div className="text-white py-12 dark:bg-[#0a1222] transition-colors duration-200" style={{ backgroundColor: 'var(--accent)' }}>
      <div className="mx-auto max-w-7xl px-3 sm:px-6 lg:px-8">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-8">
          <div className="flex-1">
            <h1 className="text-4xl md:text-5xl font-bold mb-4 uppercase leading-tight tracking-tight drop-shadow-sm">
              {title}
            </h1>
            
            {description && (
              <p className="text-lg md:text-xl opacity-90 max-w-2xl uppercase leading-relaxed mb-6">
                {description}
              </p>
            )}
            
            <div className="mt-2 flex flex-wrap items-center gap-4 text-sm opacity-90 uppercase tracking-widest">
              <span>
                {t('products_found')}: <span suppressHydrationWarning className="font-bold border-b-2 border-white/30 ml-1">{totalCount}</span>
              </span>
            </div>
          </div>
          
          <div className="flex-shrink-0 pb-1">
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
          </div>
        </div>
      </div>
    </div>
  )
}
