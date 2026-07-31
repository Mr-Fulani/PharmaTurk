import Link from 'next/link'
import { useRouter } from 'next/router'
import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'next-i18next'
import api, { getSingleFlight } from '../lib/api'
import {
  applyImageFallback,
  DEFAULT_MEDIA_FALLBACK,
  replaceFailedVideoWithFallback,
  resolveMediaUrl,
} from '../lib/media'
import { useAuth } from '../context/AuthContext'

export interface ReviewSummary {
  averageRating: number
  count: number
}

export interface QuestionSummary {
  count: number
}

export type ProductFeedbackTab = 'reviews' | 'questions'

interface ReviewMedia {
  id: number
  media_type: 'image' | 'video'
  url: string
}

interface Review {
  id: number
  author_name: string
  author_avatar_url?: string | null
  user_username: string
  rating: number
  text: string
  status: 'pending' | 'approved' | 'rejected'
  media: ReviewMedia[]
  created_at: string
}

interface ReviewResponse {
  average_rating: number
  reviews_count: number
  rating_distribution?: Record<string, number>
  reviews: Review[]
  own_review: Review | null
  can_review: boolean
}

interface ProductQuestion {
  id: number
  author_name: string
  author_avatar_url?: string | null
  user_username: string
  is_anonymous: boolean
  question: string
  answer: string
  status: 'pending' | 'answered' | 'rejected'
  created_at: string
  answered_at?: string | null
}

interface QuestionResponse {
  questions_count: number
  questions: ProductQuestion[]
  own_questions: ProductQuestion[]
}

const extractApiError = (payload: unknown, fallback: string): string => {
  if (!payload) return fallback
  if (typeof payload === 'string') {
    const message = payload.trim()
    if (/^(?:<!doctype html|<html)/i.test(message)) return fallback
    return message || fallback
  }
  if (Array.isArray(payload)) {
    for (const item of payload) {
      const message = extractApiError(item, '')
      if (message) return message
    }
    return fallback
  }
  if (typeof payload === 'object') {
    const record = payload as Record<string, unknown>
    if (typeof record.detail === 'string') return record.detail
    for (const value of Object.values(record)) {
      const message = extractApiError(value, '')
      if (message) return message
    }
  }
  return fallback
}

const Stars = ({ value, interactive = false, onChange, size = 'md' }: {
  value: number
  interactive?: boolean
  onChange?: (value: number) => void
  size?: 'sm' | 'md' | 'lg'
}) => {
  const iconSize = size === 'lg' ? 'h-7 w-7' : size === 'sm' ? 'h-4 w-4' : 'h-5 w-5'
  return (
    <span className="inline-flex gap-1" aria-label={`${value}/5`}>
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          disabled={!interactive}
          onClick={() => onChange?.(star)}
          className={`p-0 ${interactive ? 'cursor-pointer transition-transform hover:scale-110' : 'cursor-default'} ${star <= value ? 'text-amber-400' : 'text-gray-300 dark:text-gray-600'}`}
          aria-label={`${star}/5`}
        >
          <svg className={`${iconSize} fill-current`} viewBox="0 0 20 20" aria-hidden="true">
            <path d="M10 15l-5.878 3.09 1.123-6.545L.489 6.91l6.572-.955L10 0l2.939 5.955 6.572.955-4.756 4.635 1.123 6.545z" />
          </svg>
        </button>
      ))}
    </span>
  )
}

const Avatar = ({ url, label, profileHref }: { url?: string | null; label: string; profileHref?: string }) => {
  const resolvedUrl = resolveMediaUrl(url) || ''
  const avatar = !resolvedUrl ? (
      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-blue-50 text-sm font-semibold text-blue-600 dark:bg-blue-950/60 dark:text-blue-300">
        {(label.trim()[0] || '?').toUpperCase()}
      </div>
  ) : (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={resolvedUrl}
      alt=""
      className="h-11 w-11 shrink-0 rounded-full object-cover"
      onError={(event) => applyImageFallback(event.currentTarget)}
    />
  )
  if (!profileHref) return avatar
  return (
    <Link
      href={profileHref}
      aria-label={label}
      className="shrink-0 rounded-full transition-shadow hover:ring-2 hover:ring-blue-500 hover:ring-offset-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:ring-offset-gray-950"
    >
      {avatar}
    </Link>
  )
}

const ReviewMediaGrid = ({ media }: { media: ReviewMedia[] }) => (
  <div className="mt-4 flex flex-wrap gap-2">
    {media.map((item) => item.media_type === 'image' ? (
      <a key={item.id} href={resolveMediaUrl(item.url) || item.url} target="_blank" rel="noreferrer" className="h-20 w-20 overflow-hidden rounded-xl border border-gray-200 bg-gray-100 dark:border-gray-700 dark:bg-gray-900">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={resolveMediaUrl(item.url) || item.url}
          alt=""
          className="h-full w-full object-cover transition-transform hover:scale-105"
          onError={(event) => applyImageFallback(event.currentTarget)}
        />
      </a>
    ) : (
      <a key={item.id} href={resolveMediaUrl(item.url) || item.url} target="_blank" rel="noreferrer" className="relative h-20 w-20 overflow-hidden rounded-xl border border-gray-200 bg-black dark:border-gray-700">
        <video
          src={resolveMediaUrl(item.url) || item.url}
          muted
          preload="metadata"
          className="h-full w-full object-cover"
          onError={(event) => replaceFailedVideoWithFallback(event.currentTarget, '')}
        />
        <span className="absolute inset-0 flex items-center justify-center bg-black/25 text-white" aria-hidden="true">
          <svg className="h-7 w-7 fill-current" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
        </span>
      </a>
    ))}
  </div>
)

export default function ProductReviews({
  productType,
  productSlug,
  productName,
  activeTab = 'reviews',
  onTabChange,
  onSummaryChange,
  onQuestionSummaryChange,
}: {
  productType: string
  productSlug: string
  productName: string
  activeTab?: ProductFeedbackTab
  onTabChange?: (tab: ProductFeedbackTab) => void
  onSummaryChange?: (summary: ReviewSummary) => void
  onQuestionSummaryChange?: (summary: QuestionSummary) => void
}) {
  const { t, i18n } = useTranslation('common')
  const { user } = useAuth()
  const router = useRouter()
  const [reviews, setReviews] = useState<ReviewResponse | null>(null)
  const [questions, setQuestions] = useState<QuestionResponse | null>(null)
  const [reviewsLoading, setReviewsLoading] = useState(true)
  const [questionsLoading, setQuestionsLoading] = useState(true)
  const [reviewSaving, setReviewSaving] = useState(false)
  const [questionSaving, setQuestionSaving] = useState(false)
  const [editing, setEditing] = useState(false)
  const [rating, setRating] = useState(0)
  const [reviewText, setReviewText] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [questionText, setQuestionText] = useState('')
  const [questionAnonymous, setQuestionAnonymous] = useState(true)
  const [reviewError, setReviewError] = useState('')
  const [questionError, setQuestionError] = useState('')
  const [questionSuccess, setQuestionSuccess] = useState('')
  const [reviewSort, setReviewSort] = useState<'newest' | 'highest'>('newest')
  const [questionSort, setQuestionSort] = useState<'newest' | 'oldest'>('newest')

  const loadReviews = useCallback(async () => {
    setReviewsLoading(true)
    try {
      const response = await getSingleFlight('/feedback/product-reviews/', {
        params: { product_type: productType, product_slug: productSlug },
      })
      const next = response.data as ReviewResponse
      setReviews(next)
      onSummaryChange?.({ averageRating: next.average_rating, count: next.reviews_count })
    } finally {
      setReviewsLoading(false)
    }
  }, [productType, productSlug, onSummaryChange])

  const loadQuestions = useCallback(async () => {
    setQuestionsLoading(true)
    try {
      const response = await getSingleFlight('/feedback/product-questions/', {
        params: { product_type: productType, product_slug: productSlug },
      })
      const next = response.data as QuestionResponse
      setQuestions(next)
      onQuestionSummaryChange?.({ count: next.questions_count })
    } finally {
      setQuestionsLoading(false)
    }
  }, [productType, productSlug, onQuestionSummaryChange])

  useEffect(() => {
    setReviewError('')
    setQuestionError('')
    loadReviews().catch(() => setReviewError(t('product_reviews_load_error', 'Не удалось загрузить отзывы')))
    loadQuestions().catch(() => setQuestionError(t('product_questions_load_error', 'Не удалось загрузить вопросы')))
  }, [loadQuestions, loadReviews, t])

  const beginEdit = () => {
    if (!reviews?.own_review) return
    setRating(reviews.own_review.rating)
    setReviewText(reviews.own_review.text)
    setFiles([])
    setEditing(true)
    setReviewError('')
  }

  const validateFiles = (selected: File[]) => {
    const existing = editing ? (reviews?.own_review?.media.length || 0) : 0
    if (existing + selected.length > 3) return t('product_reviews_max_files', 'Можно прикрепить не более трёх файлов')
    for (const file of selected) {
      const limit = file.type.startsWith('video/') ? 50 : 10
      if (!file.type.startsWith('image/') && !file.type.startsWith('video/')) return t('product_reviews_media_types', 'Разрешены только фото и видео')
      if (file.size > limit * 1024 * 1024) return t('product_reviews_file_too_large', 'Фото — до 10 МБ, видео — до 50 МБ')
    }
    return ''
  }

  const submitReview = async (event: FormEvent) => {
    event.preventDefault()
    setReviewError('')
    if (!rating || !reviewText.trim()) {
      setReviewError(t('product_reviews_required', 'Укажите оценку и напишите текст отзыва'))
      return
    }
    const fileError = validateFiles(files)
    if (fileError) {
      setReviewError(fileError)
      return
    }
    const body = new FormData()
    body.append('product_type', productType)
    body.append('product_slug', productSlug)
    body.append('product_name', productName)
    body.append('rating', String(rating))
    body.append('text', reviewText.trim())
    files.forEach((file) => body.append('media', file))

    setReviewSaving(true)
    try {
      if (editing && reviews?.own_review) await api.patch(`/feedback/product-reviews/${reviews.own_review.id}/`, body)
      else await api.post('/feedback/product-reviews/', body)
      setEditing(false)
      setRating(0)
      setReviewText('')
      setFiles([])
      await loadReviews()
    } catch (requestError: any) {
      setReviewError(extractApiError(requestError?.response?.data, t('product_reviews_save_error', 'Не удалось сохранить отзыв')))
    } finally {
      setReviewSaving(false)
    }
  }

  const removeOwnReview = async () => {
    if (!reviews?.own_review || !window.confirm(t('product_reviews_delete_confirm', 'Удалить ваш отзыв?'))) return
    await api.delete(`/feedback/product-reviews/${reviews.own_review.id}/`)
    setEditing(false)
    await loadReviews()
  }

  const submitQuestion = async (event: FormEvent) => {
    event.preventDefault()
    setQuestionError('')
    setQuestionSuccess('')
    if (questionText.trim().length < 5) {
      setQuestionError(t('product_questions_required', 'Напишите вопрос — минимум 5 символов'))
      return
    }
    setQuestionSaving(true)
    try {
      await api.post('/feedback/product-questions/', {
        product_type: productType,
        product_slug: productSlug,
        product_name: productName,
        question: questionText.trim(),
        is_anonymous: questionAnonymous,
      })
      setQuestionText('')
      setQuestionSuccess(t('product_questions_success', 'Вопрос отправлен. Мы уведомили администратора.'))
      await loadQuestions()
    } catch (requestError: any) {
      setQuestionError(extractApiError(requestError?.response?.data, t('product_questions_save_error', 'Не удалось отправить вопрос')))
    } finally {
      setQuestionSaving(false)
    }
  }

  const sortedReviews = useMemo(() => [...(reviews?.reviews || [])].sort((left, right) => {
    if (reviewSort === 'highest' && right.rating !== left.rating) return right.rating - left.rating
    return new Date(right.created_at).getTime() - new Date(left.created_at).getTime()
  }), [reviewSort, reviews?.reviews])

  const sortedQuestions = useMemo(() => [...(questions?.questions || [])].sort((left, right) => {
    const direction = questionSort === 'newest' ? -1 : 1
    return direction * (new Date(left.created_at).getTime() - new Date(right.created_at).getTime())
  }), [questionSort, questions?.questions])

  const reviewMedia = useMemo(
    () => (reviews?.reviews || []).flatMap((review) => review.media).filter((item) => item.url).slice(0, 8),
    [reviews?.reviews],
  )

  const dateFormatter = useMemo(
    () => new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium' }),
    [i18n.language],
  )
  const loginHref = `/auth?next=${encodeURIComponent(`${router.asPath}#product-${activeTab}`)}`
  const ownReviewStatus = reviews?.own_review?.status
  const distribution = reviews?.rating_distribution || {}

  return (
    <section id="product-reviews" className="relative mt-12 scroll-mt-24 border-t border-gray-200 pt-7 dark:border-gray-700">
      <span id="product-questions" className="absolute -top-24" aria-hidden="true" />
      <div role="tablist" aria-label={t('product_feedback_tabs_label', 'Отзывы и вопросы о товаре')} className="flex gap-1 overflow-x-auto border-b border-gray-200 dark:border-gray-700">
        {(['reviews', 'questions'] as ProductFeedbackTab[]).map((tab) => {
          const selected = activeTab === tab
          const count = tab === 'reviews' ? (reviews?.reviews_count || 0) : (questions?.questions_count || 0)
          return (
            <button
              key={tab}
              type="button"
              role="tab"
              id={`product-${tab}-tab`}
              aria-controls={`product-${tab}-panel`}
              onClick={() => onTabChange?.(tab)}
              className={`flex-1 whitespace-nowrap border-b-2 px-2 py-3 text-sm font-semibold transition-colors sm:flex-none sm:px-4 sm:text-xl ${selected ? 'border-blue-600 text-gray-950 dark:text-white' : 'border-transparent text-gray-500 hover:text-blue-600 dark:text-gray-400'}`}
              aria-selected={selected}
            >
              {tab === 'reviews'
                ? t('product_reviews_tab', 'Отзывы о товаре')
                : t('product_questions_tab', 'Вопросы о товаре')}
              <sup className="ml-1 text-xs font-medium text-gray-500">{count}</sup>
            </button>
          )
        })}
      </div>

      {activeTab === 'reviews' ? (
        <div id="product-reviews-panel" role="tabpanel" aria-labelledby="product-reviews-tab" className="mt-7 grid gap-10 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="min-w-0">
            {reviews?.own_review && !editing && (
              <div className="mb-6 rounded-2xl border border-blue-100 bg-blue-50/70 px-5 py-4 dark:border-blue-900 dark:bg-blue-950/30">
                <p className="text-sm font-semibold text-blue-900 dark:text-blue-200">
                  {ownReviewStatus === 'approved'
                    ? t('product_reviews_status_approved', 'Ваш отзыв опубликован')
                    : ownReviewStatus === 'rejected'
                      ? t('product_reviews_status_rejected', 'Ваш отзыв отклонён')
                      : t('product_reviews_status_pending', 'Ваш отзыв ожидает модерации')}
                </p>
                {ownReviewStatus !== 'approved' && (
                  <div className="mt-3">
                    <Stars value={reviews.own_review.rating} />
                    <p className="mt-2 whitespace-pre-wrap text-gray-700 dark:text-gray-200">{reviews.own_review.text}</p>
                    {reviews.own_review.media.length > 0 && <ReviewMediaGrid media={reviews.own_review.media} />}
                  </div>
                )}
                <div className="mt-3 flex gap-4">
                  <button type="button" onClick={beginEdit} className="text-sm font-medium text-blue-600 hover:underline">{t('product_reviews_edit', 'Редактировать')}</button>
                  <button type="button" onClick={() => removeOwnReview().catch(() => setReviewError(t('product_reviews_delete_error', 'Не удалось удалить отзыв')))} className="text-sm font-medium text-gray-600 hover:underline dark:text-gray-300">{t('product_reviews_delete', 'Удалить')}</button>
                </div>
              </div>
            )}

            {!user && (
              <p className="mb-6 text-gray-600 dark:text-gray-300">
                <Link href={loginHref} className="font-semibold text-blue-600 hover:underline">{t('login', 'Войти')}</Link>{' '}
                {t('product_reviews_login_hint', 'чтобы оставить отзыв')}
              </p>
            )}

            {user && reviews?.can_review && (!reviews.own_review || editing) && (
              <form onSubmit={submitReview} className="mb-7 space-y-4 rounded-2xl bg-gray-50 p-5 dark:bg-gray-800/70">
                <div>
                  <label className="mb-2 block text-sm font-semibold text-gray-800 dark:text-gray-100">{t('product_reviews_rating', 'Ваша оценка')}</label>
                  <Stars value={rating} interactive onChange={setRating} size="lg" />
                </div>
                <div>
                  <label htmlFor="product-review-text" className="mb-2 block text-sm font-semibold text-gray-800 dark:text-gray-100">{t('product_reviews_text', 'Ваш отзыв')}</label>
                  <textarea id="product-review-text" value={reviewText} onChange={(event) => setReviewText(event.target.value)} maxLength={5000} rows={4} className="w-full rounded-xl border border-gray-300 bg-white px-4 py-3 text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100 dark:border-gray-600 dark:bg-gray-900 dark:text-white dark:focus:ring-blue-950" />
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <label htmlFor="product-review-media" className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-blue-200 bg-white px-4 py-2.5 text-sm font-semibold text-blue-700 hover:bg-blue-50 dark:border-blue-800 dark:bg-gray-900 dark:text-blue-300">
                    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 16V4m0 0L8 8m4-4l4 4M4 15v4a1 1 0 001 1h14a1 1 0 001-1v-4" /></svg>
                    <span>{files.length ? t('product_reviews_files_selected', 'Выбрано файлов: {{count}}', { count: files.length }) : t('product_reviews_choose_files', 'Выбрать файлы')}</span>
                    <input id="product-review-media" type="file" accept="image/*,video/*" multiple onChange={(event) => setFiles(Array.from(event.target.files || []))} className="sr-only" />
                  </label>
                  <button disabled={reviewSaving} className="rounded-xl bg-blue-600 px-5 py-2.5 font-semibold text-white hover:bg-blue-700 disabled:opacity-60">{reviewSaving ? t('product_reviews_saving', 'Сохранение...') : t('product_reviews_submit', 'Отправить')}</button>
                  {editing && <button type="button" onClick={() => setEditing(false)} className="rounded-xl border border-gray-300 px-5 py-2.5 dark:border-gray-600">{t('cancel', 'Отмена')}</button>}
                </div>
                {files.length > 0 && <p className="truncate text-xs text-gray-500" title={files.map((file) => file.name).join(', ')}>{files.map((file) => file.name).join(', ')}</p>}
                {reviewError && <p className="text-sm text-red-600">{reviewError}</p>}
              </form>
            )}

            {reviewMedia.length > 0 && <ReviewMediaGrid media={reviewMedia} />}

            <div className="mt-6 flex flex-wrap items-center gap-3 border-b border-gray-200 pb-4 dark:border-gray-700">
              <span className="text-sm font-medium text-gray-700 dark:text-gray-200">{t('product_reviews_sort_label', 'Показать сначала:')}</span>
              <button type="button" onClick={() => setReviewSort('newest')} className={`text-sm font-semibold ${reviewSort === 'newest' ? 'text-blue-600' : 'text-gray-500 hover:text-blue-600'}`}>{t('product_reviews_sort_newest', 'новые')}</button>
              <button type="button" onClick={() => setReviewSort('highest')} className={`text-sm font-semibold ${reviewSort === 'highest' ? 'text-blue-600' : 'text-gray-500 hover:text-blue-600'}`}>{t('product_reviews_sort_highest', 'с высокой оценкой')}</button>
            </div>

            {reviewError && !(user && reviews?.can_review && (!reviews.own_review || editing)) && <p className="mt-4 text-sm text-red-600">{reviewError}</p>}
            <div className="divide-y divide-gray-200 dark:divide-gray-700">
              {reviewsLoading ? (
                <p className="py-8 text-gray-500">{t('loading', 'Загрузка...')}</p>
              ) : sortedReviews.length ? sortedReviews.map((review) => {
                const authorLabel = review.author_name || t('product_questions_name_hidden', 'Имя скрыто')
                const profileHref = review.user_username ? `/user/${encodeURIComponent(review.user_username)}` : undefined
                const author = profileHref ? (
                  <Link href={profileHref} className="font-semibold text-gray-950 hover:text-blue-600 dark:text-white">{authorLabel}</Link>
                ) : <span className="font-semibold text-gray-950 dark:text-white">{authorLabel}</span>
                return (
                  <article key={review.id} className="py-7">
                    <div className="flex items-start gap-3">
                      <Avatar url={review.author_avatar_url} label={authorLabel} profileHref={profileHref} />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <div>{author}<div className="mt-1 sm:hidden"><Stars value={review.rating} size="sm" /></div></div>
                          <div className="flex items-center gap-4"><time className="text-xs text-gray-500">{dateFormatter.format(new Date(review.created_at))}</time><span className="hidden sm:inline-flex"><Stars value={review.rating} size="sm" /></span></div>
                        </div>
                        <p className="mt-4 whitespace-pre-wrap leading-relaxed text-gray-800 dark:text-gray-100">{review.text}</p>
                        {review.media.length > 0 && <ReviewMediaGrid media={review.media} />}
                      </div>
                    </div>
                  </article>
                )
              }) : (
                <p className="py-8 text-gray-600 dark:text-gray-300">{t('product_reviews_empty', 'Пока нет отзывов. Будьте первым!')}</p>
              )}
            </div>
          </div>

          <aside className="h-fit rounded-2xl border border-gray-200 p-5 dark:border-gray-700 lg:sticky lg:top-24">
            <div className="flex items-center justify-between gap-4">
              <Stars value={Math.round(reviews?.average_rating || 0)} size="lg" />
              <strong className="text-2xl text-gray-950 dark:text-white">{(reviews?.average_rating || 0).toFixed(1)} / 5</strong>
            </div>
            <p className="mt-4 border-t border-gray-200 pt-4 text-sm leading-relaxed text-gray-500 dark:border-gray-700 dark:text-gray-400">{t('product_reviews_based_on', 'Рейтинг формируется на основе опубликованных отзывов')}</p>
            <div className="mt-5 space-y-2.5">
              {[5, 4, 3, 2, 1].map((star) => {
                const count = Number(distribution[String(star)] || 0)
                const percent = reviews?.reviews_count ? Math.round((count / reviews.reviews_count) * 100) : 0
                return (
                  <div key={star} className="grid grid-cols-[58px_1fr_auto] items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
                    <span>{t('product_reviews_stars_short', { count: star, defaultValue: '{{count}} звёзд' })}</span>
                    <span className="h-1.5 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700"><span className="block h-full rounded-full bg-amber-400" style={{ width: `${percent}%` }} /></span>
                    <span className="min-w-5 text-right text-gray-700 dark:text-gray-200">{count}</span>
                  </div>
                )
              })}
            </div>
            <p className="mt-8 text-sm leading-relaxed text-gray-500 dark:text-gray-400">{t('product_reviews_verified_note', 'Отзывы могут оставлять только пользователи, купившие товар. Так формируется честный рейтинг.')}</p>
          </aside>
        </div>
      ) : (
        <div id="product-questions-panel" role="tabpanel" aria-labelledby="product-questions-tab" className="mt-7 grid gap-10 lg:grid-cols-[minmax(0,1fr)_300px]">
          <div className="min-w-0">
            <div className="rounded-2xl bg-slate-50 p-5 dark:bg-slate-900/70 sm:p-6">
              <h3 className="text-xl font-semibold text-gray-950 dark:text-white">{t('product_questions_ask_title', 'Задайте вопрос о товаре')}</h3>
              <p className="mt-2 text-sm leading-relaxed text-gray-600 dark:text-gray-300">{t('product_questions_ask_description', 'Администратор уточнит информацию и опубликует ответ. Мы уже получим уведомление после отправки вопроса.')}</p>
              {user ? (
                <form onSubmit={submitQuestion} className="mt-5">
                  <textarea
                    value={questionText}
                    onChange={(event) => setQuestionText(event.target.value)}
                    maxLength={2000}
                    rows={3}
                    placeholder={t('product_questions_placeholder', 'Напишите свой вопрос')}
                    className="w-full resize-y rounded-xl border border-gray-300 bg-white px-4 py-3 text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100 dark:border-gray-600 dark:bg-gray-950 dark:text-white dark:focus:ring-blue-950"
                  />
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                    <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
                      <input type="checkbox" checked={questionAnonymous} onChange={(event) => setQuestionAnonymous(event.target.checked)} className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                      {t('product_questions_hide_name', 'Скрыть моё имя')}
                    </label>
                    <button disabled={questionSaving} className="rounded-xl bg-blue-600 px-5 py-2.5 font-semibold text-white hover:bg-blue-700 disabled:opacity-60">{questionSaving ? t('product_questions_sending', 'Отправка...') : t('product_questions_submit', 'Отправить вопрос')}</button>
                  </div>
                  {questionError && <p className="mt-3 text-sm text-red-600">{questionError}</p>}
                  {questionSuccess && <p className="mt-3 text-sm font-medium text-green-600 dark:text-green-400">{questionSuccess}</p>}
                </form>
              ) : (
                <p className="mt-5 text-gray-600 dark:text-gray-300"><Link href={loginHref} className="font-semibold text-blue-600 hover:underline">{t('login', 'Войти')}</Link>{' '}{t('product_questions_login_hint', 'чтобы задать вопрос')}</p>
              )}
            </div>

            {questions?.own_questions.map((question) => (
              <div key={question.id} className="mt-5 rounded-2xl border border-blue-100 bg-blue-50/60 p-5 dark:border-blue-900 dark:bg-blue-950/30">
                <p className="text-sm font-semibold text-blue-900 dark:text-blue-200">
                  {question.status === 'rejected' ? t('product_questions_status_rejected', 'Ваш вопрос отклонён') : t('product_questions_status_pending', 'Ваш вопрос ожидает ответа')}
                </p>
                <p className="mt-2 whitespace-pre-wrap text-gray-800 dark:text-gray-100">{question.question}</p>
              </div>
            ))}

            <div className="mt-6 flex justify-end border-b border-gray-200 pb-4 dark:border-gray-700">
              <select value={questionSort} onChange={(event) => setQuestionSort(event.target.value as 'newest' | 'oldest')} className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-200">
                <option value="newest">{t('product_questions_sort_newest', 'Сначала новые')}</option>
                <option value="oldest">{t('product_questions_sort_oldest', 'Сначала старые')}</option>
              </select>
            </div>

            {questionError && !user && <p className="mt-4 text-sm text-red-600">{questionError}</p>}
            <div className="divide-y divide-gray-200 dark:divide-gray-700">
              {questionsLoading ? (
                <p className="py-8 text-gray-500">{t('loading', 'Загрузка...')}</p>
              ) : sortedQuestions.length ? sortedQuestions.map((question) => {
                const authorLabel = question.author_name || t('product_questions_name_hidden', 'Имя скрыто')
                const profileHref = question.user_username ? `/user/${encodeURIComponent(question.user_username)}` : undefined
                const author = profileHref ? (
                  <Link href={profileHref} className="font-medium text-gray-500 hover:text-blue-600 dark:hover:text-blue-400">{authorLabel}</Link>
                ) : <span className="font-medium text-gray-500">{authorLabel}</span>
                return (
                  <article key={question.id} className="py-7">
                    <div className="flex gap-3">
                      <Avatar url={question.author_avatar_url} label={authorLabel} profileHref={profileHref} />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                          {author}
                          <time className="text-xs text-gray-500">{dateFormatter.format(new Date(question.created_at))}</time>
                        </div>
                        <h4 className="mt-2 whitespace-pre-wrap text-lg font-semibold leading-snug text-gray-950 dark:text-white">{question.question}</h4>
                        <div className="mt-5 border-l-2 border-green-500 pl-5">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="inline-flex items-center gap-2 font-semibold text-gray-950 dark:text-white">
                              {/* eslint-disable-next-line @next/next/no-img-element */}
                              <img
                                src={DEFAULT_MEDIA_FALLBACK}
                                alt="Mudaroba"
                                className="h-8 w-8 rounded-full bg-gray-100 object-cover dark:bg-gray-800"
                                onError={(event) => applyImageFallback(event.currentTarget)}
                              />
                              Mudaroba
                            </span>
                            {question.answered_at && <time className="text-xs text-gray-500">{dateFormatter.format(new Date(question.answered_at))}</time>}
                          </div>
                          <p className="mt-3 whitespace-pre-wrap leading-relaxed text-gray-700 dark:text-gray-200">{question.answer}</p>
                        </div>
                      </div>
                    </div>
                  </article>
                )
              }) : (
                <p className="py-8 text-gray-600 dark:text-gray-300">{t('product_questions_empty', 'Пока нет опубликованных вопросов. Задайте первый!')}</p>
              )}
            </div>
          </div>

          <aside className="h-fit rounded-2xl border border-amber-300 bg-amber-50 p-5 text-sm leading-relaxed text-amber-900 shadow-sm dark:border-amber-500/35 dark:bg-amber-950/30 dark:text-amber-200 lg:sticky lg:top-24">
            <h3 className="font-semibold text-amber-900 dark:text-amber-100">{t('product_questions_sidebar_title', 'О чём можно спросить?')}</h3>
            <p className="mt-3">{t('product_questions_sidebar_text', 'Уточните характеристики, комплектацию, совместимость или особенности использования товара. Вопросы о доставке и заказе лучше направить в поддержку.')}</p>
          </aside>
        </div>
      )}
    </section>
  )
}
