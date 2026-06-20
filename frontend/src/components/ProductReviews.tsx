import Link from 'next/link'
import { useRouter } from 'next/router'
import { FormEvent, useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'next-i18next'
import api from '../lib/api'
import { resolveMediaUrl } from '../lib/media'
import { useAuth } from '../context/AuthContext'

export interface ReviewSummary {
  averageRating: number
  count: number
}

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
  reviews: Review[]
  own_review: Review | null
  can_review: boolean
}

const Stars = ({ value, interactive = false, onChange }: { value: number; interactive?: boolean; onChange?: (value: number) => void }) => (
  <span className="inline-flex gap-1" aria-label={`${value}/5`}>
    {[1, 2, 3, 4, 5].map((star) => (
      <button
        key={star}
        type="button"
        disabled={!interactive}
        onClick={() => onChange?.(star)}
        className={`p-0 ${interactive ? 'cursor-pointer' : 'cursor-default'} ${star <= value ? 'text-amber-400' : 'text-gray-300'}`}
        aria-label={`${star}/5`}
      >
        <svg className="h-5 w-5 fill-current" viewBox="0 0 20 20" aria-hidden="true">
          <path d="M10 15l-5.878 3.09 1.123-6.545L.489 6.91l6.572-.955L10 0l2.939 5.955 6.572.955-4.756 4.635 1.123 6.545z" />
        </svg>
      </button>
    ))}
  </span>
)

export default function ProductReviews({
  productType,
  productSlug,
  productName,
  onSummaryChange,
}: {
  productType: string
  productSlug: string
  productName: string
  onSummaryChange?: (summary: ReviewSummary) => void
}) {
  const { t, i18n } = useTranslation('common')
  const { user } = useAuth()
  const router = useRouter()
  const [data, setData] = useState<ReviewResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState(false)
  const [rating, setRating] = useState(0)
  const [text, setText] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const response = await api.get('/feedback/product-reviews/', {
        params: { product_type: productType, product_slug: productSlug },
      })
      const next = response.data as ReviewResponse
      setData(next)
      onSummaryChange?.({ averageRating: next.average_rating, count: next.reviews_count })
    } finally {
      setLoading(false)
    }
  }, [productType, productSlug, onSummaryChange])

  useEffect(() => {
    load().catch(() => setError(t('product_reviews_load_error', 'Не удалось загрузить отзывы')))
  }, [load, t])

  const beginEdit = () => {
    if (!data?.own_review) return
    setRating(data.own_review.rating)
    setText(data.own_review.text)
    setFiles([])
    setEditing(true)
    setError('')
  }

  const validateFiles = (selected: File[]) => {
    const existing = editing ? (data?.own_review?.media.length || 0) : 0
    if (existing + selected.length > 3) return t('product_reviews_max_files', 'Можно прикрепить не более трёх файлов')
    for (const file of selected) {
      const limit = file.type.startsWith('video/') ? 50 : 10
      if (!file.type.startsWith('image/') && !file.type.startsWith('video/')) return t('product_reviews_media_types', 'Разрешены только фото и видео')
      if (file.size > limit * 1024 * 1024) return t('product_reviews_file_too_large', 'Фото — до 10 МБ, видео — до 50 МБ')
    }
    return ''
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    if (!rating || !text.trim()) {
      setError(t('product_reviews_required', 'Укажите оценку и напишите текст отзыва'))
      return
    }
    const fileError = validateFiles(files)
    if (fileError) {
      setError(fileError)
      return
    }
    const body = new FormData()
    body.append('product_type', productType)
    body.append('product_slug', productSlug)
    body.append('product_name', productName)
    body.append('rating', String(rating))
    body.append('text', text.trim())
    files.forEach((file) => body.append('media', file))

    setSaving(true)
    try {
      if (editing && data?.own_review) {
        await api.patch(`/feedback/product-reviews/${data.own_review.id}/`, body)
      } else {
        await api.post('/feedback/product-reviews/', body)
      }
      setEditing(false)
      setRating(0)
      setText('')
      setFiles([])
      await load()
    } catch (requestError: any) {
      const payload = requestError?.response?.data
      setError(payload?.detail || payload?.media?.[0] || t('product_reviews_save_error', 'Не удалось сохранить отзыв'))
    } finally {
      setSaving(false)
    }
  }

  const removeOwnReview = async () => {
    if (!data?.own_review || !window.confirm(t('product_reviews_delete_confirm', 'Удалить ваш отзыв?'))) return
    await api.delete(`/feedback/product-reviews/${data.own_review.id}/`)
    setEditing(false)
    await load()
  }

  const ownStatus = data?.own_review?.status
  const loginHref = `/auth?next=${encodeURIComponent(`${router.asPath}#product-reviews`)}`

  return (
    <section id="product-reviews" className="mt-10 scroll-mt-24 rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold text-gray-900 dark:text-white">{t('product_reviews_title', 'Отзывы')}</h2>
          {data && data.reviews_count > 0 && (
            <div className="mt-2 flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
              <Stars value={Math.round(data.average_rating)} />
              <span>{data.average_rating.toFixed(1)} ({data.reviews_count})</span>
            </div>
          )}
        </div>
      </div>

      {data?.own_review && !editing && (
        <div className="mt-5 rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-600 dark:bg-gray-900/40">
          <p className="text-sm font-medium text-gray-700 dark:text-gray-200">
            {ownStatus === 'approved'
              ? t('product_reviews_status_approved', 'Ваш отзыв опубликован')
              : ownStatus === 'rejected'
                ? t('product_reviews_status_rejected', 'Ваш отзыв отклонён')
                : t('product_reviews_status_pending', 'Ваш отзыв ожидает модерации')}
          </p>
          <div className="mt-3 flex gap-3">
            <button type="button" onClick={beginEdit} className="text-sm font-medium text-red-600 hover:underline">{t('edit', 'Редактировать')}</button>
            <button type="button" onClick={() => removeOwnReview().catch(() => setError(t('product_reviews_delete_error', 'Не удалось удалить отзыв')))} className="text-sm font-medium text-gray-600 hover:underline dark:text-gray-300">{t('delete', 'Удалить')}</button>
          </div>
        </div>
      )}

      {!user && (
        <p className="mt-5 text-gray-600 dark:text-gray-300">
          <Link href={loginHref} className="font-medium text-red-600 hover:underline">{t('login', 'Войти')}</Link>{' '}
          {t('product_reviews_login_hint', 'чтобы оставить отзыв')}
        </p>
      )}

      {user && data?.can_review && (!data.own_review || editing) && (
        <form onSubmit={submit} className="mt-5 space-y-4 rounded-xl border border-gray-200 p-4 dark:border-gray-600">
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-800 dark:text-gray-100">{t('product_reviews_rating', 'Ваша оценка')}</label>
            <Stars value={rating} interactive onChange={setRating} />
          </div>
          <div>
            <label htmlFor="product-review-text" className="mb-2 block text-sm font-medium text-gray-800 dark:text-gray-100">{t('product_reviews_text', 'Ваш отзыв')}</label>
            <textarea id="product-review-text" value={text} onChange={(event) => setText(event.target.value)} maxLength={5000} rows={5} className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 focus:border-red-500 focus:outline-none dark:border-gray-600 dark:bg-gray-900 dark:text-white" />
          </div>
          <div>
            <label htmlFor="product-review-media" className="mb-2 block text-sm font-medium text-gray-800 dark:text-gray-100">{t('product_reviews_media', 'Фото или видео (до 3 файлов)')}</label>
            <input id="product-review-media" type="file" accept="image/*,video/*" multiple onChange={(event) => setFiles(Array.from(event.target.files || []))} className="block w-full text-sm text-gray-600 file:mr-3 file:rounded-md file:border-0 file:bg-gray-100 file:px-3 file:py-2 dark:text-gray-300 dark:file:bg-gray-700" />
            <p className="mt-1 text-xs text-gray-500">{t('product_reviews_media_limits', 'Фото до 10 МБ, видео до 50 МБ')}</p>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex gap-3">
            <button disabled={saving} className="rounded-lg bg-red-600 px-5 py-2.5 font-medium text-white hover:bg-red-700 disabled:opacity-60">{saving ? t('saving', 'Сохранение...') : t('product_reviews_submit', 'Отправить на модерацию')}</button>
            {editing && <button type="button" onClick={() => setEditing(false)} className="rounded-lg border border-gray-300 px-5 py-2.5 dark:border-gray-600">{t('cancel', 'Отмена')}</button>}
          </div>
        </form>
      )}

      {error && !editing && <p className="mt-4 text-sm text-red-600">{error}</p>}

      <div className="mt-6 space-y-5">
        {loading ? (
          <p className="text-gray-500">{t('loading', 'Загрузка...')}</p>
        ) : data?.reviews.length ? data.reviews.map((review) => (
          <article key={review.id} className="border-t border-gray-200 pt-5 first:border-0 first:pt-0 dark:border-gray-700">
            <div className="flex items-start gap-3">
              {review.author_avatar_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={resolveMediaUrl(review.author_avatar_url) || ''} alt="" className="h-10 w-10 rounded-full object-cover" />
              ) : <div className="h-10 w-10 rounded-full bg-gray-200 dark:bg-gray-700" />}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Link href={`/user/${encodeURIComponent(review.user_username)}`} className="font-medium text-gray-900 hover:text-red-600 dark:text-white">{review.author_name}</Link>
                  <time className="text-xs text-gray-500">{new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium' }).format(new Date(review.created_at))}</time>
                </div>
                <div className="mt-1"><Stars value={review.rating} /></div>
                <p className="mt-3 whitespace-pre-wrap text-gray-700 dark:text-gray-200">{review.text}</p>
                {review.media.length > 0 && (
                  <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
                    {review.media.map((media) => media.media_type === 'image' ? (
                      <a key={media.id} href={resolveMediaUrl(media.url) || media.url} target="_blank" rel="noreferrer">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={resolveMediaUrl(media.url) || media.url} alt="" className="aspect-square w-full rounded-lg object-cover" />
                      </a>
                    ) : (
                      <video key={media.id} src={resolveMediaUrl(media.url) || media.url} controls preload="metadata" className="aspect-square w-full rounded-lg bg-black object-contain" />
                    ))}
                  </div>
                )}
              </div>
            </div>
          </article>
        )) : (
          <p className="text-gray-600 dark:text-gray-300">{t('product_reviews_empty', 'Пока нет отзывов. Будьте первым!')}</p>
        )}
      </div>
    </section>
  )
}
