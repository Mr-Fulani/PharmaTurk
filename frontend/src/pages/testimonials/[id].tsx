import { useState } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import { GetServerSideProps } from 'next'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { ChevronLeftIcon, ChevronRightIcon, StarIcon } from '@heroicons/react/20/solid'
import { SITE_NAME, SITE_URL } from '../../lib/siteMeta'
import { getInternalApiUrl } from '../../lib/urls'
import { getPlaceholderImageUrl, resolveMediaUrl } from '../../lib/media'
import { buildTestimonialUrl, Testimonial } from '../../lib/testimonials'

interface TestimonialDetailProps {
  testimonial: Testimonial
}

export default function TestimonialDetailPage({ testimonial }: TestimonialDetailProps) {
  const { t } = useTranslation('common')
  const [currentMediaIndex, setCurrentMediaIndex] = useState(0)
  const currentMedia = testimonial.media[currentMediaIndex] || null
  const plainText = testimonial.text.replace(/\s+/g, ' ').trim()
  const shortDescription = plainText.length > 160
    ? `${plainText.slice(0, 157).replace(/\s+\S*$/, '')}...`
    : plainText
  const pageTitle = `${t('testimonials_page_title', 'Отзывы клиентов')} — ${testimonial.author_name} — ${SITE_NAME}`
  const description = shortDescription || t('testimonials_page_description', 'Что говорят наши клиенты о наших товарах и услугах')
  const metaKeywords = [
    t('testimonials_page_title', 'Отзывы клиентов'),
    t('footer_testimonials_tooltip', 'Отзывы'),
    testimonial.author_name,
    SITE_NAME,
    'отзывы клиентов',
    'customer reviews',
  ].filter(Boolean).join(', ')
  const canonicalUrl = `${SITE_URL}${buildTestimonialUrl(testimonial.id)}`
  const ogImage = `${SITE_URL}/footer-testimonials-promo.png`

  const nextMedia = () => {
    if (testimonial.media.length > 1) {
      setCurrentMediaIndex((prev) => (prev + 1) % testimonial.media.length)
    }
  }

  const prevMedia = () => {
    if (testimonial.media.length > 1) {
      setCurrentMediaIndex((prev) => (prev - 1 + testimonial.media.length) % testimonial.media.length)
    }
  }

  return (
    <>
      <Head>
        <title>{pageTitle}</title>
        <meta name="description" content={description} />
        <meta name="keywords" content={metaKeywords} />
        <link rel="canonical" href={canonicalUrl} />
        <link rel="alternate" hrefLang="ru" href={canonicalUrl} />
        <link rel="alternate" hrefLang="en" href={`${SITE_URL}/en${buildTestimonialUrl(testimonial.id)}`} />
        <link rel="alternate" hrefLang="x-default" href={canonicalUrl} />
        <meta property="og:title" content={pageTitle} />
        <meta property="og:description" content={description} />
        <meta property="og:url" content={canonicalUrl} />
        <meta property="og:type" content="article" />
        <meta property="og:image" content={ogImage} />
        <meta property="twitter:card" content="summary_large_image" />
        <meta property="twitter:title" content={pageTitle} />
        <meta property="twitter:description" content={description} />
        <meta property="twitter:image" content={ogImage} />
      </Head>

      <main className="min-h-screen bg-gray-50 py-10">
        <div className="mx-auto max-w-6xl px-4">
          <div className="mb-6">
            <Link
              href="/testimonials"
              className="inline-flex items-center gap-2 text-sm text-gray-600 transition-colors hover:text-red-600"
            >
              <ChevronLeftIcon className="h-4 w-4" />
              {t('back_to_testimonials', 'Вернуться к отзывам')}
            </Link>
          </div>

          <article className="overflow-hidden rounded-[28px] border border-gray-200 bg-white shadow-sm">
            <div className="grid grid-cols-1 gap-0 lg:grid-cols-[1.1fr_0.9fr]">
              <div className="relative bg-gray-100">
                {currentMedia ? (
                  <div className="relative aspect-[4/5] md:aspect-[16/12] lg:aspect-[4/5]">
                    {currentMedia.media_type === 'image' && currentMedia.image_url && (
                      <img
                        src={resolveMediaUrl(currentMedia.image_url)}
                        alt={testimonial.author_name}
                        className="h-full w-full object-cover"
                      />
                    )}
                    {currentMedia.media_type === 'video_file' && currentMedia.video_file_url && (
                      <video
                        controls
                        playsInline
                        className="h-full w-full object-cover"
                      >
                        <source src={resolveMediaUrl(currentMedia.video_file_url)} type="video/mp4" />
                      </video>
                    )}
                    {currentMedia.media_type === 'video' && currentMedia.video_url && (
                      <div className="flex h-full items-center justify-center bg-gray-900 p-6 text-center text-sm text-white">
                        <a
                          href={currentMedia.video_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="rounded-full border border-white/30 px-4 py-2 transition hover:bg-white/10"
                        >
                          {t('view_details', 'Узнать подробнее')}
                        </a>
                      </div>
                    )}

                    {testimonial.media.length > 1 && (
                      <>
                        <button
                          type="button"
                          onClick={prevMedia}
                          className="absolute left-4 top-1/2 -translate-y-1/2 rounded-full bg-black/45 p-2 text-white transition hover:bg-black/65"
                          aria-label="Previous media"
                        >
                          <ChevronLeftIcon className="h-5 w-5" />
                        </button>
                        <button
                          type="button"
                          onClick={nextMedia}
                          className="absolute right-4 top-1/2 -translate-y-1/2 rounded-full bg-black/45 p-2 text-white transition hover:bg-black/65"
                          aria-label="Next media"
                        >
                          <ChevronRightIcon className="h-5 w-5" />
                        </button>
                      </>
                    )}
                  </div>
                ) : (
                  <div className="aspect-[4/5] md:aspect-[16/12] lg:aspect-[4/5]">
                    <img
                      src={getPlaceholderImageUrl({ type: 'testimonial', id: testimonial.id })}
                      alt={testimonial.author_name}
                      className="h-full w-full object-cover"
                    />
                  </div>
                )}

                {testimonial.media.length > 1 && (
                  <div className="flex gap-2 overflow-x-auto px-4 py-4">
                    {testimonial.media.map((media, index) => {
                      const thumb = media.image_url
                        ? resolveMediaUrl(media.image_url)
                        : getPlaceholderImageUrl({ type: 'testimonial', id: `${testimonial.id}-${media.id}` })
                      return (
                        <button
                          key={media.id}
                          type="button"
                          onClick={() => setCurrentMediaIndex(index)}
                          className={`h-16 w-16 shrink-0 overflow-hidden rounded-xl border ${index === currentMediaIndex ? 'border-red-500' : 'border-gray-200'}`}
                        >
                          <img src={thumb} alt="" className="h-full w-full object-cover" />
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>

              <div className="flex flex-col justify-between p-6 md:p-8">
                <div>
                  <div className="mb-5 flex items-start gap-4">
                    {testimonial.author_avatar_url && (
                      <img
                        src={resolveMediaUrl(testimonial.author_avatar_url)}
                        alt={testimonial.author_name}
                        className="h-14 w-14 rounded-full object-cover"
                      />
                    )}
                    <div>
                      <h1 className="text-3xl font-bold text-gray-900">{testimonial.author_name}</h1>
                      <p className="mt-1 text-sm text-gray-500">
                        {new Date(testimonial.created_at).toLocaleDateString('ru-RU')}
                      </p>
                    </div>
                  </div>

                  {testimonial.rating && (
                    <div className="mb-6 flex items-center gap-1">
                      {[0, 1, 2, 3, 4].map((rating) => (
                        <StarIcon
                          key={rating}
                          className={`h-5 w-5 ${(testimonial.rating || 0) > rating ? 'text-yellow-400' : 'text-gray-300'}`}
                        />
                      ))}
                    </div>
                  )}

                  <div className="rounded-[24px] bg-gray-50 p-5">
                    <p className="whitespace-pre-wrap text-base leading-8 text-gray-700">
                      {testimonial.text}
                    </p>
                  </div>
                </div>

                <div className="mt-8 flex flex-wrap gap-3">
                  <Link
                    href="/testimonials"
                    className="inline-flex items-center rounded-full border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 transition hover:border-red-300 hover:text-red-600"
                  >
                    {t('back_to_testimonials', 'Вернуться к отзывам')}
                  </Link>
                  {testimonial.user_username && (
                    <Link
                      href={`/user/${testimonial.user_username}?testimonial_id=${testimonial.id}`}
                      className="inline-flex items-center rounded-full bg-red-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-700"
                    >
                      {testimonial.author_name}
                    </Link>
                  )}
                </div>
              </div>
            </div>
          </article>
        </div>
      </main>
    </>
  )
}

export const getServerSideProps: GetServerSideProps = async ({ locale, params }) => {
  const id = Array.isArray(params?.id) ? params?.id[0] : params?.id
  if (!id) return { notFound: true }

  try {
    const response = await fetch(getInternalApiUrl(`feedback/testimonials/${encodeURIComponent(String(id))}/`))
    if (!response.ok) {
      return { notFound: true }
    }
    const testimonial = await response.json()

    return {
      props: {
        ...(await serverSideTranslations(locale || 'ru', ['common'])),
        testimonial,
      },
    }
  } catch (error) {
    console.error('SSR testimonial detail fetch failed:', error)
    return { notFound: true }
  }
}
