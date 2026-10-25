import dynamic from 'next/dynamic'
import Link from 'next/link'
import { GetServerSideProps } from 'next'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { LazyMotion, domAnimation, m, useReducedMotion } from 'framer-motion'
import type { LucideIcon } from 'lucide-react'
import {
  ArrowRight,
  Baby,
  BadgeCheck,
  Ban,
  Bike,
  CheckCircle2,
  FileText,
  HeartPulse,
  Home,
  Hotel,
  Languages,
  Leaf,
  MapPin,
  MessageCircle,
  Pill,
  Search,
  Send,
  ShieldCheck,
  Stethoscope,
  Thermometer,
  Wallet,
} from 'lucide-react'

import SEO from '../components/SEO'
import IstanbulDeliveryMap from '../components/IstanbulDeliveryMap'
import { FaqList } from '../components/BlogArticleBody'
import {
  ISTANBUL_DELIVERY_PATH,
  buildIstanbulDeliverySchemas,
  istanbulDeliveryContent,
} from '../content/istanbulDelivery'
import { fetchFooterSettings } from '../lib/footerSettings'
import { appendWhatsappText } from '../lib/medicineMarketCheck'
import { SITE_NAME, SITE_URL } from '../lib/siteMeta'

const SourcingRequestForm = dynamic(() => import('../components/SourcingRequestForm'), { ssr: false })

type Contacts = { whatsapp_url: string; telegram_url: string }

const ICONS: Record<string, LucideIcon> = {
  languages: Languages,
  map: MapPin,
  pill: Pill,
  heart: HeartPulse,
  hotel: Hotel,
  stethoscope: Stethoscope,
  home: Home,
  baby: Baby,
  file: FileText,
  leaf: Leaf,
  thermometer: Thermometer,
  message: MessageCircle,
  search: Search,
  check: CheckCircle2,
  bike: Bike,
  badge: BadgeCheck,
  wallet: Wallet,
  shield: ShieldCheck,
}

const sectionTitle = 'text-2xl font-bold text-main md:text-3xl'
const card = 'rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 shadow-sm md:p-6'
const ctaPrimary =
  'inline-flex items-center justify-center gap-2 rounded-xl bg-[var(--accent)] px-6 py-3.5 text-base font-semibold text-white shadow-md transition-all hover:-translate-y-0.5 hover:bg-[var(--accent-strong)] hover:shadow-lg'
const ctaSecondary =
  'inline-flex items-center justify-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-6 py-3.5 text-base font-semibold text-main transition-colors hover:border-[var(--accent)] hover:text-[var(--accent)]'

function IconBadge({ name, className = '' }: { name: string; className?: string }) {
  const Icon = ICONS[name] || Pill
  return (
    <span className={`inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-[var(--accent)]/10 text-[var(--accent)] ${className}`}>
      <Icon className="h-6 w-6" aria-hidden="true" />
    </span>
  )
}

/** Блок, появляющийся при прокрутке (без анимации при «уменьшить движение»). */
function Reveal({ children, className = '', delay = 0 }: { children: React.ReactNode; className?: string; delay?: number }) {
  const reduceMotion = useReducedMotion()
  return (
    <m.div
      className={className}
      initial={reduceMotion ? false : { opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '0px 0px -40px 0px' }}
      transition={{ duration: 0.35, ease: 'easeOut', delay }}
    >
      {children}
    </m.div>
  )
}

function ContactButtons({ contacts, content, center = false }: { contacts: Contacts; content: ReturnType<typeof istanbulDeliveryContent>; center?: boolean }) {
  const whatsappHref = contacts.whatsapp_url ? appendWhatsappText(contacts.whatsapp_url, content.whatsappText) : ''
  return (
    <div className={`flex flex-col gap-3 sm:flex-row sm:flex-wrap ${center ? 'sm:justify-center' : ''}`}>
      {whatsappHref && (
        <a href={whatsappHref} target="_blank" rel="noopener noreferrer" className={ctaPrimary}>
          <MessageCircle className="h-5 w-5" aria-hidden="true" />
          {content.ctaWhatsapp}
        </a>
      )}
      {contacts.telegram_url && (
        <a href={contacts.telegram_url} target="_blank" rel="noopener noreferrer" className={whatsappHref ? ctaSecondary : ctaPrimary}>
          <Send className="h-5 w-5" aria-hidden="true" />
          {content.ctaTelegram}
        </a>
      )}
      <a href="#request" className={ctaSecondary}>
        {content.ctaRequest}
        <ArrowRight className="h-5 w-5" aria-hidden="true" />
      </a>
    </div>
  )
}

function HeroVisual({ content }: { content: ReturnType<typeof istanbulDeliveryContent> }) {
  const reduceMotion = useReducedMotion()
  const float = (delay: number) =>
    reduceMotion ? {} : { animate: { y: [0, -10, 0] }, transition: { duration: 4, repeat: Infinity, ease: 'easeInOut' as const, delay } }
  return (
    <div className="relative mx-auto w-full max-w-md">
      <div className="absolute -inset-6 rounded-[40px] bg-[var(--accent)]/10 blur-2xl" aria-hidden="true" />
      <m.div
        className={`${card} relative`}
        initial={reduceMotion ? false : { opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5, delay: 0.2 }}
      >
        <div className="flex items-center gap-3">
          <IconBadge name="message" />
          <p className="text-lg font-bold text-main">{content.heroCard.title}</p>
        </div>
        <dl className="mt-4 space-y-3">
          {content.heroCard.rows.map(([label, value]) => (
            <div key={label} className="flex items-baseline justify-between gap-3 border-b border-dashed border-[var(--border)] pb-2 text-sm">
              <dt className="text-main/60">{label}</dt>
              <dd className="text-right font-medium text-main">{value}</dd>
            </div>
          ))}
        </dl>
        <div className="mt-4 flex items-center gap-3 rounded-xl bg-[var(--bg)] p-3">
          <Bike className="h-6 w-6 shrink-0 text-[var(--accent)]" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-main">{content.heroCard.status}</p>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-[var(--border)]">
              <m.div
                className="h-full rounded-full bg-[var(--accent)]"
                initial={reduceMotion ? false : { width: '15%' }}
                animate={reduceMotion ? { width: '70%' } : { width: ['15%', '85%', '15%'] }}
                transition={reduceMotion ? undefined : { duration: 6, repeat: Infinity, ease: 'easeInOut' }}
              />
            </div>
          </div>
        </div>
      </m.div>
      <m.span {...float(0)} className="absolute -left-4 -top-5 hidden rounded-2xl bg-[var(--surface)] p-3 text-[var(--accent)] shadow-md sm:block" aria-hidden="true">
        <Pill className="h-7 w-7" />
      </m.span>
      <m.span {...float(1.2)} className="absolute -right-3 top-10 hidden rounded-2xl bg-[var(--surface)] p-3 text-[var(--accent)] shadow-md sm:block" aria-hidden="true">
        <Hotel className="h-7 w-7" />
      </m.span>
      <m.span {...float(2.4)} className="absolute -bottom-5 right-12 hidden rounded-2xl bg-[var(--surface)] p-3 text-[var(--accent)] shadow-md sm:block" aria-hidden="true">
        <MapPin className="h-7 w-7" />
      </m.span>
    </div>
  )
}

function BadgeMarquee({ badges }: { badges: string[] }) {
  const reduceMotion = useReducedMotion()
  const item = (text: string, key: string) => (
    <span key={key} className="inline-flex shrink-0 items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--surface)] px-4 py-2 text-sm font-medium text-main">
      <CheckCircle2 className="h-4 w-4 text-[var(--accent)]" aria-hidden="true" />
      {text}
    </span>
  )
  if (reduceMotion) {
    return <div className="flex flex-wrap justify-center gap-2">{badges.map((text) => item(text, text))}</div>
  }
  return (
    <div className="relative overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_8%,black_92%,transparent)]">
      <m.div
        className="flex w-max gap-3"
        animate={{ x: ['0%', '-50%'] }}
        transition={{ duration: 28, repeat: Infinity, ease: 'linear' }}
      >
        {[...badges, ...badges].map((text, index) => item(text, `${text}-${index}`))}
      </m.div>
    </div>
  )
}

export default function IstanbulDeliveryPage({ contacts }: { contacts: Contacts }) {
  const { t } = useTranslation('common')
  const { locale = 'ru', defaultLocale = 'ru' } = useRouter()
  const localePrefix = locale === defaultLocale ? '' : `/${locale}`
  const content = istanbulDeliveryContent(locale)
  const reduceMotion = useReducedMotion()

  return (
    <LazyMotion features={domAnimation}>
      <SEO
        title={content.metaTitle}
        description={content.metaDescription}
        canonical={ISTANBUL_DELIVERY_PATH}
        structuredData={buildIstanbulDeliverySchemas({ siteUrl: SITE_URL, localePrefix, content, siteName: SITE_NAME })}
      />
      <main className="min-h-screen overflow-x-hidden bg-page text-main">
        <div className="mx-auto max-w-6xl px-4 py-4 sm:px-6 sm:py-8">
          <nav aria-label={t('breadcrumbs', 'Хлебные крошки')} className="mb-6 flex flex-wrap items-center gap-2 text-sm text-main">
            <Link href="/" className="transition-colors hover:text-[var(--accent)]">{t('breadcrumb_home', 'Главная')}</Link>
            <span className="text-main/60">/</span>
            <span className="min-w-0 truncate font-medium">{content.breadcrumb}</span>
          </nav>

          {/* Первый экран */}
          <section className="grid items-center gap-10 lg:grid-cols-[1.15fr_1fr]">
            <div>
              <h1 className="text-3xl font-bold leading-tight text-main md:text-5xl">{content.h1}</h1>
              <p className="mt-4 text-base leading-relaxed text-main/75 md:text-lg">{content.lead}</p>
              <div className="mt-6">
                <ContactButtons contacts={contacts} content={content} />
              </div>
            </div>
            <HeroVisual content={content} />
          </section>

          <div className="mt-10 md:mt-14">
            <BadgeMarquee badges={content.badges} />
          </div>

          {/* Боли → решения */}
          <section className="mt-14 md:mt-20" aria-labelledby="istd-pains">
            <Reveal>
              <h2 id="istd-pains" className={`${sectionTitle} text-center`}>{content.painsTitle}</h2>
              <p className="mx-auto mt-3 max-w-2xl text-center text-main/70">{content.painsSubtitle}</p>
            </Reveal>
            <div className="mt-8 grid gap-4 md:grid-cols-2">
              {content.pains.map((item, index) => (
                <Reveal key={item.pain} delay={0.05 * index} className={`${card} flex gap-4`}>
                  <IconBadge name={item.icon} />
                  <div>
                    <p className="text-sm text-main/60 line-through decoration-[var(--accent)]/40">{item.pain}</p>
                    <p className="mt-2 flex gap-2 font-medium leading-relaxed text-main">
                      <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-[var(--accent)]" aria-hidden="true" />
                      <span>{item.solution}</span>
                    </p>
                  </div>
                </Reveal>
              ))}
            </div>
          </section>

          {/* Кому подходит */}
          <section className="mt-14 md:mt-20" aria-labelledby="istd-audience">
            <Reveal>
              <h2 id="istd-audience" className={`${sectionTitle} text-center`}>{content.audienceTitle}</h2>
            </Reveal>
            <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {content.audience.map((item, index) => (
                <Reveal key={item.title} delay={0.05 * index} className={`${card} group transition-all hover:-translate-y-1 hover:border-[var(--accent)]`}>
                  <IconBadge name={item.icon} className="transition-transform group-hover:scale-110" />
                  <h3 className="mt-4 text-lg font-bold text-main">{item.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-main/75">{item.text}</p>
                </Reveal>
              ))}
            </div>
          </section>

          {/* Шаги */}
          <section className="mt-14 md:mt-20" aria-labelledby="istd-steps">
            <Reveal>
              <h2 id="istd-steps" className={`${sectionTitle} text-center`}>{content.stepsTitle}</h2>
            </Reveal>
            <ol className="relative mt-8 grid gap-4 md:grid-cols-4">
              <span className="absolute left-[12%] right-[12%] top-6 hidden border-t-2 border-dashed border-[var(--accent)]/40 md:block" aria-hidden="true" />
              {content.steps.map((step, index) => {
                const Icon = ICONS[step.icon] || Pill
                return (
                  <m.li
                    key={step.title}
                    className={`${card} relative h-full`}
                    initial={reduceMotion ? false : { opacity: 0, y: 16 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: '0px 0px -40px 0px' }}
                    transition={{ duration: 0.35, ease: 'easeOut', delay: 0.06 * index }}
                  >
                    <span className="relative z-10 flex h-12 w-12 items-center justify-center rounded-full bg-[var(--accent)] text-white shadow-md">
                      <Icon className="h-6 w-6" aria-hidden="true" />
                    </span>
                    <p className="mt-4 text-xs font-semibold uppercase tracking-wide text-[var(--accent)]">{index + 1}</p>
                    <h3 className="mt-1 text-lg font-bold text-main">{step.title}</h3>
                    <p className="mt-2 text-sm leading-relaxed text-main/75">{step.text}</p>
                  </m.li>
                )
              })}
            </ol>
          </section>

          {/* Карта */}
          <section className="mt-14 grid items-center gap-8 md:mt-20 lg:grid-cols-[1fr_1.4fr]" aria-labelledby="istd-map">
            <Reveal>
              <h2 id="istd-map" className={sectionTitle}>{content.mapTitle}</h2>
              <p className="mt-3 leading-relaxed text-main/75">{content.mapText}</p>
              <ul className="mt-5 flex flex-wrap gap-2">
                {Object.values(content.districts as Record<string, string>).map((name) => (
                  <li key={name} className="rounded-full border border-[var(--border)] bg-[var(--surface)] px-3 py-1 text-sm text-main/80">{name}</li>
                ))}
              </ul>
            </Reveal>
            <Reveal delay={0.1}>
              <IstanbulDeliveryMap texts={content} />
            </Reveal>
          </section>

          {/* Что привозим и что нет */}
          <section className="mt-14 md:mt-20" aria-labelledby="istd-catalog">
            <Reveal>
              <h2 id="istd-catalog" className={`${sectionTitle} text-center`}>{content.catalogTitle}</h2>
            </Reveal>
            <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {content.catalog.map((item, index) => (
                <Reveal key={item.title} delay={0.05 * index} className={card}>
                  <IconBadge name={item.icon} />
                  <h3 className="mt-4 text-lg font-bold text-main">{item.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-main/75">{item.text}</p>
                </Reveal>
              ))}
            </div>
            <Reveal className="mt-4">
              <div className="flex flex-col gap-3 rounded-2xl border border-amber-300 bg-amber-50 p-5 text-amber-950 dark:border-amber-700/60 dark:bg-amber-950/30 dark:text-amber-100 sm:flex-row sm:items-start">
                <Ban className="h-6 w-6 shrink-0" aria-hidden="true" />
                <div>
                  <h3 className="font-bold">{content.restrictedTitle}</h3>
                  <p className="mt-1 text-sm leading-relaxed">
                    {content.restrictedText}{' '}
                    <Link href={content.restrictedLink.href} className="font-medium underline underline-offset-2">{content.restrictedLink.label}</Link>
                  </p>
                </div>
              </div>
            </Reveal>
          </section>

          {/* Доверие */}
          <section className="mt-14 md:mt-20" aria-labelledby="istd-trust">
            <Reveal>
              <h2 id="istd-trust" className={`${sectionTitle} text-center`}>{content.trustTitle}</h2>
            </Reveal>
            <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {content.trust.map((item, index) => (
                <Reveal key={item.title} delay={0.05 * index} className={`${card} text-center`}>
                  <IconBadge name={item.icon} className="mx-auto" />
                  <h3 className="mt-4 text-lg font-bold text-main">{item.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-main/75">{item.text}</p>
                </Reveal>
              ))}
            </div>
            <p className="mt-4 text-center text-sm text-main/60">{content.analogNote}</p>
          </section>

          {/* Финальный призыв */}
          <Reveal className="mt-14 md:mt-20">
            <section className="relative overflow-hidden rounded-3xl bg-[var(--accent)] px-6 py-10 text-center text-white shadow-lg md:px-12">
              <div className="absolute -right-10 -top-10 h-40 w-40 rounded-full bg-white/10" aria-hidden="true" />
              <div className="absolute -bottom-12 -left-8 h-36 w-36 rounded-full bg-white/10" aria-hidden="true" />
              <h2 className="relative text-2xl font-bold md:text-3xl">{content.finalTitle}</h2>
              <p className="relative mx-auto mt-3 max-w-xl text-white/85">{content.finalText}</p>
              <div className="relative mt-6 flex flex-col gap-3 sm:flex-row sm:justify-center">
                {contacts.whatsapp_url && (
                  <a
                    href={appendWhatsappText(contacts.whatsapp_url, content.whatsappText)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-white px-6 py-3.5 font-semibold text-[var(--accent)] transition-transform hover:-translate-y-0.5"
                  >
                    <MessageCircle className="h-5 w-5" aria-hidden="true" />
                    {content.ctaWhatsapp}
                  </a>
                )}
                {contacts.telegram_url && (
                  <a
                    href={contacts.telegram_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/60 px-6 py-3.5 font-semibold text-white transition-colors hover:bg-white/10"
                  >
                    <Send className="h-5 w-5" aria-hidden="true" />
                    {content.ctaTelegram}
                  </a>
                )}
              </div>
            </section>
          </Reveal>

          <div className="mt-14 grid gap-8 md:mt-20 lg:grid-cols-[1.4fr_1fr]">
            <FaqList title={content.faqTitle} faq={content.faq} />
            <aside className={`${card} h-fit`}>
              <h2 className="text-xl font-semibold text-main">{content.usefulTitle}</h2>
              <ul className="mt-4 space-y-3">
                {content.useful.map((link) => (
                  <li key={link.href}>
                    <Link href={link.href} className="group flex items-center justify-between gap-3 text-main transition-colors hover:text-[var(--accent)]">
                      <span>{link.label}</span>
                      <ArrowRight className="h-4 w-4 shrink-0 transition-transform group-hover:translate-x-1" aria-hidden="true" />
                    </Link>
                  </li>
                ))}
              </ul>
            </aside>
          </div>

          <div id="request" className="mt-14 scroll-mt-24 md:mt-20">
            <SourcingRequestForm
              placement="istanbul_delivery"
              initialComment={content.formComment}
              title={content.formTitle}
              subtitle={content.formSubtitle}
            />
          </div>
        </div>
      </main>
    </LazyMotion>
  )
}

export const getServerSideProps: GetServerSideProps = async (ctx) => {
  const locale = ctx.locale ?? 'ru'
  const footer = await fetchFooterSettings()
  return {
    props: {
      contacts: {
        whatsapp_url: footer.whatsapp_url || '',
        telegram_url: footer.telegram_url || '',
      },
      ...(await serverSideTranslations(locale, ['common'])),
    },
  }
}
