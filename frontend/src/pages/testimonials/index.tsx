import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useTranslation } from 'next-i18next'
import { GetServerSideProps } from 'next'
import api from '../../lib/api'
import { StarIcon, ChevronLeftIcon, ChevronRightIcon, XMarkIcon } from '@heroicons/react/20/solid'
import { PhotoIcon, VideoCameraIcon } from '@heroicons/react/24/outline'

interface TestimonialMedia {
  id: number
  media_type: 'image' | 'video' | 'video_file'
  image_url: string | null
  video_url: string | null
  video_file_url: string | null
  order: number
}

interface Testimonial {
  id: number
  author_name: string
  author_avatar_url: string | null
  text: string
  rating: number | null
  media_type: 'none' | 'image' | 'video'
  image_url: string | null
  video_url: string | null
  video_file_url: string | null
  media: TestimonialMedia[]
  created_at: string
}

interface MediaItem {
  type: 'image' | 'video' | 'video_file'
  file?: File
  url?: string
  preview?: string
}

export default function TestimonialsPage() {
  const { t } = useTranslation('common')
  const router = useRouter()
  const [testimonials, setTestimonials] = useState<Testimonial[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedTestimonial, setSelectedTestimonial] = useState<Testimonial | null>(null)
  const [currentMediaIndex, setCurrentMediaIndex] = useState(0)
  const [showForm, setShowForm] = useState(false)
  const modalRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  
  // Form state
  const [formData, setFormData] = useState({
    author_name: '',
    text: '',
    rating: 0,
  })
  const [mediaItems, setMediaItems] = useState<MediaItem[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [touchStart, setTouchStart] = useState(0)
  const [touchEnd, setTouchEnd] = useState(0)
  const [showSuccessMessage, setShowSuccessMessage] = useState(false)

  useEffect(() => {
    const fetchTestimonials = async () => {
      try {
        const response = await api.get('/feedback/testimonials/')
        const data = response.data
        setTestimonials(Array.isArray(data) ? data : data.results || [])
      } catch (error) {
        console.error('Failed to fetch testimonials:', error)
      } finally {
        setLoading(false)
      }
    }
    fetchTestimonials()
  }, [])

  // Блокировка скролла при открытом модальном окне
  useEffect(() => {
    if (selectedTestimonial) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = 'unset'
    }

    return () => {
      document.body.style.overflow = 'unset'
    }
  }, [selectedTestimonial])

  const allMedia = selectedTestimonial 
    ? (selectedTestimonial.media && selectedTestimonial.media.length > 0 
        ? selectedTestimonial.media 
        : (() => {
            // Обработка старых отзывов - определяем тип медиа по наличию полей
            if (selectedTestimonial.media_type === 'none') return []
            
            let mediaType: 'image' | 'video' | 'video_file' = 'image'
            
            if (selectedTestimonial.video_file_url) {
              mediaType = 'video_file'
            } else if (selectedTestimonial.video_url) {
              mediaType = 'video'
            } else if (selectedTestimonial.image_url) {
              mediaType = 'image'
            } else {
              return []
            }
            
            return [{
              id: selectedTestimonial.id,
              media_type: mediaType,
              image_url: selectedTestimonial.image_url,
              video_url: selectedTestimonial.video_url,
              video_file_url: selectedTestimonial.video_file_url,
              order: 0
            }]
          })())
    : []

  const nextMedia = () => {
    if (allMedia.length > 0) {
      setCurrentMediaIndex((prev) => (prev + 1) % allMedia.length)
    }
  }

  const prevMedia = () => {
    if (allMedia.length > 0) {
      setCurrentMediaIndex((prev) => (prev - 1 + allMedia.length) % allMedia.length)
    }
  }

  const handleTouchStart = (e: React.TouchEvent) => {
    setTouchStart(e.targetTouches[0].clientX)
  }

  const handleTouchMove = (e: React.TouchEvent) => {
    setTouchEnd(e.targetTouches[0].clientX)
  }

  const handleTouchEnd = () => {
    if (!touchStart || !touchEnd) return
    
    const distance = touchStart - touchEnd
    const isLeftSwipe = distance > 50
    const isRightSwipe = distance < -50

    if (isLeftSwipe && allMedia.length > 0) {
      nextMedia()
    }
    if (isRightSwipe && allMedia.length > 0) {
      prevMedia()
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>, type: 'image' | 'video_file') => {
    const files = e.target.files
    if (files) {
      const newItems: MediaItem[] = []
      for (let i = 0; i < files.length; i++) {
        const file = files[i]
        const item: MediaItem = {
          type,
          file,
          preview: type === 'image' ? URL.createObjectURL(file) : undefined
        }
        newItems.push(item)
      }
      setMediaItems([...mediaItems, ...newItems])
    }
  }

  const removeMediaItem = (index: number) => {
    const item = mediaItems[index]
    if (item.preview) {
      URL.revokeObjectURL(item.preview)
    }
    setMediaItems(mediaItems.filter((_, i) => i !== index))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)

    try {
      const formDataToSend = new FormData()
      formDataToSend.append('author_name', formData.author_name)
      formDataToSend.append('text', formData.text)
      if (formData.rating > 0) {
        formDataToSend.append('rating', formData.rating.toString())
      }

      // Добавляем медиа файлы
      mediaItems.forEach((item, index) => {
        if (item.type === 'image' && item.file) {
          formDataToSend.append(`media_type_${index}`, 'image')
          formDataToSend.append(`media_image_${index}`, item.file)
        } else if (item.type === 'video_file' && item.file) {
          formDataToSend.append(`media_type_${index}`, 'video_file')
          formDataToSend.append(`media_video_file_${index}`, item.file)
        } else if (item.type === 'video' && item.url) {
          formDataToSend.append(`media_type_${index}`, 'video')
          formDataToSend.append(`media_video_url_${index}`, item.url)
        }
      })

      const response = await api.post('/feedback/testimonials/', formDataToSend, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      })

      // Сброс формы
      setFormData({ author_name: '', text: '', rating: 0 })
      setMediaItems([])
      setShowForm(false)
      
      // Показываем сообщение об успешной отправке и модерации
      setShowSuccessMessage(true)
      setTimeout(() => {
        setShowSuccessMessage(false)
      }, 5000) // Скрываем через 5 секунд
      
      // Обновляем список отзывов (только активные)
      const updatedResponse = await api.get('/feedback/testimonials/')
      const updatedData = updatedResponse.data
      setTestimonials(Array.isArray(updatedData) ? updatedData : updatedData.results || [])
    } catch (error) {
      console.error('Failed to submit testimonial:', error)
      alert(t('testimonial_submit_error', 'Ошибка при отправке отзыва. Попробуйте еще раз.'))
    } finally {
      setSubmitting(false)
    }
  }

  const renderMedia = (media: TestimonialMedia) => {
    if (media.media_type === 'image' && media.image_url) {
      return (
        <img
          src={media.image_url}
          alt={selectedTestimonial?.author_name || 'Testimonial'}
          className="w-full h-full object-cover"
        />
      )
    }
    
    if (media.media_type === 'video' && media.video_url) {
      let embedUrl = media.video_url
      if (embedUrl.includes('youtube.com/watch?v=') || embedUrl.includes('youtu.be/')) {
        const youtubeRegex = /(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})/
        const match = embedUrl.match(youtubeRegex)
        if (match) {
          embedUrl = `https://www.youtube.com/embed/${match[1]}?controls=1`
        }
      } else if (embedUrl.includes('vimeo.com/')) {
        const vimeoRegex = /(?:vimeo\.com\/)(\d+)/
        const match = embedUrl.match(vimeoRegex)
        if (match) {
          embedUrl = `https://player.vimeo.com/video/${match[1]}?controls=1`
        }
      }
      
      return (
        <iframe
          src={embedUrl}
          title="Testimonial video"
          frameBorder="0"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
          className="w-full h-full"
        />
      )
    }
    
    if (media.media_type === 'video_file' && media.video_file_url) {
      return (
        <video
          controls
          playsInline
          className="w-full h-full object-cover"
        >
          <source src={media.video_file_url} type="video/mp4" />
          {t('video_tag_unsupported', 'Ваш браузер не поддерживает видео.')}
        </video>
      )
    }
    
    return null
  }

  const extractYouTubeId = (url: string): string | null => {
    const youtubeRegex = /(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})/
    const match = url.match(youtubeRegex)
    return match ? match[1] : null
  }

  const extractVimeoId = (url: string): string | null => {
    const vimeoRegex = /vimeo\.com\/(?:video\/)?(\d+)/
    const match = url.match(vimeoRegex)
    return match ? match[1] : null
  }

  const getExternalVideoThumbnail = (url: string): string | null => {
    const youtubeId = extractYouTubeId(url)
    if (youtubeId) {
      return `https://img.youtube.com/vi/${youtubeId}/hqdefault.jpg`
    }

    const vimeoId = extractVimeoId(url)
    if (vimeoId) {
      return `https://vumbnail.com/${vimeoId}.jpg`
    }

    return null
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-500">{t('loading', 'Загрузка...')}</div>
      </div>
    )
  }

  return (
    <>
      <Head>
        <title>{t('testimonials_page_title', 'Отзывы клиентов')} - PharmaTurk</title>
      </Head>
      
      {/* Success notification */}
      {showSuccessMessage && (
        <div className="fixed top-4 right-4 z-50 animate-slide-in">
          <div className="bg-green-50 border border-green-200 rounded-lg shadow-lg p-4 max-w-md">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <svg className="h-6 w-6 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div className="ml-3 flex-1">
                <h3 className="text-sm font-medium text-green-800">
                  {t('testimonial_submitted_title', 'Отзыв отправлен!')}
                </h3>
                <p className="mt-1 text-sm text-green-700">
                  {t('testimonial_moderation_message', 'Спасибо за ваш отзыв! Он отправлен на модерацию и будет опубликован после проверки администратором.')}
                </p>
              </div>
              <div className="ml-4 flex-shrink-0">
                <button
                  onClick={() => setShowSuccessMessage(false)}
                  className="inline-flex text-green-400 hover:text-green-600 focus:outline-none"
                >
                  <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      
      <div className="min-h-screen bg-gray-50 py-12">
        <div className="mx-auto max-w-6xl px-4">
          <div className="mb-8">
            <h1 className="text-4xl font-bold text-gray-900 mb-4">
              {t('testimonials_page_title', 'Отзывы клиентов')}
            </h1>
            <p className="text-gray-600">
              {t('testimonials_page_description', 'Что говорят наши клиенты о наших товарах и услугах')}
            </p>
          </div>

          {testimonials.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-500 text-lg">
                {t('no_testimonials', 'Пока нет отзывов')}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {testimonials.map((testimonial) => (
                <div
                  key={testimonial.id}
                  onClick={() => {
                    setSelectedTestimonial(testimonial)
                    setCurrentMediaIndex(0)
                  }}
                  className="bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-xl transition-all duration-300 overflow-hidden group cursor-pointer transform hover:-translate-y-2"
                >
                  {(() => {
                    // Определяем медиа для отображения в карточке
                    let cardMedia: TestimonialMedia | null = null
                    
                    if (testimonial.media && testimonial.media.length > 0) {
                      cardMedia = testimonial.media[0]
                    } else if (testimonial.media_type !== 'none') {
                      // Обработка старых отзывов
                      let mediaType: 'image' | 'video' | 'video_file' = 'image'
                      
                      if (testimonial.video_file_url) {
                        mediaType = 'video_file'
                      } else if (testimonial.video_url) {
                        mediaType = 'video'
                      } else if (testimonial.image_url) {
                        mediaType = 'image'
                      } else {
                        return null
                      }
                      
                      cardMedia = {
                        id: testimonial.id,
                        media_type: mediaType,
                        image_url: testimonial.image_url,
                        video_url: testimonial.video_url,
                        video_file_url: testimonial.video_file_url,
                        order: 0
                      }
                    }
                    
                    if (!cardMedia) return null
                    
                    return (
                      <div className="relative w-full aspect-[9/16] overflow-hidden bg-gray-100 rounded-xl">
                        {cardMedia.media_type === 'image' && cardMedia.image_url && (
                          <img
                            src={cardMedia.image_url}
                            alt={testimonial.author_name}
                            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-110"
                          />
                        )}
                        {cardMedia.media_type === 'video' && cardMedia.video_url && (
                          (() => {
                            const thumbnail = getExternalVideoThumbnail(cardMedia.video_url || '')
                            if (thumbnail) {
                              return (
                                <img
                                  src={thumbnail}
                                  alt={testimonial.author_name}
                                  className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-110"
                                />
                              )
                            }
                            return (
                              <div className="w-full h-full flex items-center justify-center bg-gray-900 text-white">
                                {t('video_preview_unavailable', 'Предпросмотр недоступен')}
                              </div>
                            )
                          })()
                        )}
                        {cardMedia.media_type === 'video_file' && cardMedia.video_file_url && (
                          <video
                            src={`${cardMedia.video_file_url}#t=0.5`}
                            muted
                            playsInline
                            preload="metadata"
                            className="w-full h-full object-cover"
                          />
                        )}
                      </div>
                    )
                  })()}
                  
                  <div className="p-4">
                    {testimonial.rating && (
                      <div className="flex items-center mb-2">
                        {[0, 1, 2, 3, 4].map((rating) => (
                          <StarIcon
                            key={rating}
                            className={`h-4 w-4 ${
                              (testimonial.rating || 0) > rating
                                ? 'text-yellow-400'
                                : 'text-gray-300'
                            }`}
                          />
                        ))}
                      </div>
                    )}
                    <p className="text-gray-600 mb-3 text-sm line-clamp-3">
                      "{testimonial.text}"
                    </p>
                    <div className="flex items-center">
                      {testimonial.author_avatar_url && (
                        <img
                          src={testimonial.author_avatar_url}
                          alt={testimonial.author_name}
                          className="w-8 h-8 rounded-full mr-3 object-cover"
                        />
                      )}
                      <div className="text-xs font-semibold text-gray-900">
                        {testimonial.author_name}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Add Testimonial Button */}
          <div className="text-center mt-12 mb-8">
            <button
              onClick={() => setShowForm(!showForm)}
              className="px-6 py-3 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
            >
              {showForm ? t('cancel', 'Отмена') : t('add_testimonial', 'Оставить отзыв')}
            </button>
          </div>

          {/* Add Testimonial Form */}
          {showForm && (
            <div className="bg-white rounded-xl shadow-lg p-6 mb-12">
              <h2 className="text-2xl font-bold text-gray-900 mb-6">
                {t('add_testimonial', 'Оставить отзыв')}
              </h2>
              
              <form onSubmit={handleSubmit} className="space-y-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    {t('your_name', 'Ваше имя')} *
                  </label>
                  <input
                    type="text"
                    required
                    value={formData.author_name}
                    onChange={(e) => setFormData({ ...formData, author_name: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 focus:border-transparent"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    {t('rating', 'Рейтинг')}
                  </label>
                  <div className="flex items-center gap-2">
                    {[1, 2, 3, 4, 5].map((rating) => (
                      <button
                        key={rating}
                        type="button"
                        onClick={() => setFormData({ ...formData, rating })}
                        className={`p-2 rounded ${
                          formData.rating >= rating
                            ? 'text-yellow-400'
                            : 'text-gray-300 hover:text-yellow-300'
                        }`}
                      >
                        <StarIcon className="w-6 h-6" />
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    {t('testimonial_text', 'Текст отзыва')} *
                  </label>
                  <textarea
                    required
                    rows={6}
                    value={formData.text}
                    onChange={(e) => setFormData({ ...formData, text: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 focus:border-transparent"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    {t('add_media', 'Добавить медиа')}
                  </label>
                  
                  <div className="space-y-4">
                    {/* Image upload */}
                    <div>
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                      >
                        <PhotoIcon className="w-5 h-5" />
                        {t('add_image', 'Добавить изображение')}
                      </button>
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept="image/*"
                        multiple
                        onChange={(e) => handleFileChange(e, 'image')}
                        className="hidden"
                      />
                    </div>

                    {/* Video file upload */}
                    <div>
                      <button
                        type="button"
                        onClick={() => {
                          const input = document.createElement('input')
                          input.type = 'file'
                          input.accept = 'video/*'
                          input.multiple = true
                          input.onchange = (e) => handleFileChange(e as any, 'video_file')
                          input.click()
                        }}
                        className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                      >
                        <VideoCameraIcon className="w-5 h-5" />
                        {t('add_video_file', 'Добавить видео файл')}
                      </button>
                    </div>

                    {/* Video URL */}
                    <div>
                      <input
                        type="url"
                        placeholder={t('video_url_placeholder', 'URL видео (YouTube, Vimeo)')}
                        onBlur={(e) => {
                          if (e.target.value) {
                            setMediaItems([...mediaItems, { type: 'video', url: e.target.value }])
                            e.target.value = ''
                          }
                        }}
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 focus:border-transparent"
                      />
                    </div>

                    {/* Media previews */}
                    {mediaItems.length > 0 && (
                      <div className="grid grid-cols-3 gap-4">
                        {mediaItems.map((item, index) => (
                          <div key={index} className="relative">
                            {item.type === 'image' && item.preview && (
                              <img
                                src={item.preview}
                                alt={`Preview ${index + 1}`}
                                className="w-full h-32 object-cover rounded-lg"
                              />
                            )}
                            {item.type === 'video_file' && (
                              <div className="w-full h-32 bg-gray-200 rounded-lg flex items-center justify-center">
                                <VideoCameraIcon className="w-8 h-8 text-gray-400" />
                              </div>
                            )}
                            {item.type === 'video' && item.url && (
                              <div className="w-full h-32 bg-gray-200 rounded-lg flex items-center justify-center">
                                <span className="text-sm text-gray-600 truncate px-2">{item.url}</span>
                              </div>
                            )}
                            <button
                              type="button"
                              onClick={() => removeMediaItem(index)}
                              className="absolute top-2 right-2 p-1 bg-red-600 text-white rounded-full hover:bg-red-700"
                            >
                              <XMarkIcon className="w-4 h-4" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={submitting}
                  className="w-full px-6 py-3 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {submitting ? t('submitting', 'Отправка...') : t('submit_testimonial', 'Отправить отзыв')}
                </button>
              </form>
            </div>
          )}
        </div>
      </div>

      {/* Modal for testimonial detail */}
      {selectedTestimonial && (
        <div 
          className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
          onClick={() => {
            setSelectedTestimonial(null)
            setCurrentMediaIndex(0)
          }}
        >
          <div
            ref={modalRef}
            className="bg-white rounded-3xl shadow-2xl w-full max-w-3xl max-h-[90vh] overflow-y-auto relative"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Close button */}
            <button
              onClick={() => {
                setSelectedTestimonial(null)
                setCurrentMediaIndex(0)
              }}
              className="absolute top-4 right-4 z-10 p-2 bg-black/50 hover:bg-black/70 text-white rounded-full transition-all"
            >
              <XMarkIcon className="w-6 h-6" />
            </button>

            <div className="flex flex-col items-center gap-6 p-6">
              {/* Media Slider */}
              {allMedia.length > 0 && allMedia[currentMediaIndex] && (
                <div 
                  className="relative w-full max-w-sm aspect-[9/16] bg-black rounded-2xl overflow-hidden"
                  onTouchStart={handleTouchStart}
                  onTouchMove={handleTouchMove}
                  onTouchEnd={handleTouchEnd}
                >
                  {renderMedia(allMedia[currentMediaIndex])}
                  
                  {allMedia.length > 1 && (
                    <>
                      <button
                        onClick={prevMedia}
                        className="absolute left-3 top-1/2 -translate-y-1/2 p-2 bg-black/50 hover:bg-black/70 text-white rounded-full transition-all z-10"
                        aria-label="Previous media"
                      >
                        <ChevronLeftIcon className="w-5 h-5" />
                      </button>
                      <button
                        onClick={nextMedia}
                        className="absolute right-3 top-1/2 -translate-y-1/2 p-2 bg-black/50 hover:bg-black/70 text-white rounded-full transition-all z-10"
                        aria-label="Next media"
                      >
                        <ChevronRightIcon className="w-5 h-5" />
                      </button>
                      
                      {/* Media indicators */}
                      <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex gap-2 z-10">
                        {allMedia.map((_, index) => (
                          <button
                            key={index}
                            onClick={() => setCurrentMediaIndex(index)}
                            className={`w-2 h-2 rounded-full transition-all ${
                              index === currentMediaIndex ? 'bg-white' : 'bg-white/50'
                            }`}
                            aria-label={`Go to media ${index + 1}`}
                          />
                        ))}
                      </div>
                    </>
                  )}
                </div>
              )}

              {/* Content */}
              <div className="w-full space-y-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-center">
                    {selectedTestimonial.author_avatar_url && (
                      <img
                        src={selectedTestimonial.author_avatar_url}
                        alt={selectedTestimonial.author_name}
                        className="w-12 h-12 rounded-full mr-4 object-cover"
                      />
                    )}
                    <div>
                      <h2 className="text-2xl font-bold text-gray-900">{selectedTestimonial.author_name}</h2>
                      <p className="text-sm text-gray-500">
                        {new Date(selectedTestimonial.created_at).toLocaleDateString('ru-RU')}
                      </p>
                    </div>
                  </div>
                  
                  {selectedTestimonial.rating && (
                    <div className="flex items-center">
                      {[0, 1, 2, 3, 4].map((rating) => (
                        <StarIcon
                          key={rating}
                          className={`h-5 w-5 ${
                            (selectedTestimonial.rating || 0) > rating
                              ? 'text-yellow-400'
                              : 'text-gray-300'
                          }`}
                        />
                      ))}
                    </div>
                  )}
                </div>
                
                <p className="text-gray-700 text-lg leading-relaxed whitespace-pre-wrap">
                  {selectedTestimonial.text}
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
      <style jsx>{`
        @keyframes slide-in {
          from {
            transform: translateX(100%);
            opacity: 0;
          }
          to {
            transform: translateX(0);
            opacity: 1;
          }
        }
        .animate-slide-in {
          animation: slide-in 0.3s ease-out;
        }
      `}</style>
    </>
  )
}

export const getServerSideProps: GetServerSideProps = async ({ locale }) => {
  return {
    props: {
      ...(await serverSideTranslations(locale || 'ru', ['common'])),
    },
  }
}

