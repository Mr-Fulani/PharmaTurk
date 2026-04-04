import LazyYouTubeCard from './LazyYouTubeCard'
import FallbackMediaImage from './FallbackMediaImage'
import InViewAutoplayVideo from './InViewAutoplayVideo'
import {
  resolveMediaUrl,
  getPlaceholderImageUrl,
  isVideoUrl,
  extractYouTubeId,
  getYouTubeCardThumbnailUrl,
} from '../lib/media'

const MASONRY_IMAGE_SIZES = '(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw'

export type CardMasonryPlaceholderType = 'brand' | 'category'

export type CardMasonryMediaProps = {
  mediaUrl?: string | null
  alt: string
  placeholderType: CardMasonryPlaceholderType
  id?: number
}

/**
 * Медиа для плитки бренда/категории (masonry): ленивый YouTube, in-view видео, оптимизированные картинки.
 */
export default function CardMasonryMedia({ mediaUrl, alt, placeholderType, id }: CardMasonryMediaProps) {
  const effectiveUrl = mediaUrl || getPlaceholderImageUrl({ type: placeholderType, id })

  const youtubeId = extractYouTubeId(effectiveUrl)
  if (youtubeId) {
    const thumb = getYouTubeCardThumbnailUrl(effectiveUrl)
    return <LazyYouTubeCard youtubeId={youtubeId} youtubeThumb={thumb} alt={alt} />
  }

  const src = resolveMediaUrl(effectiveUrl)
  if (!src) return null

  const placeholder = id ? getPlaceholderImageUrl({ type: placeholderType, id }) : undefined

  if (isVideoUrl(mediaUrl || effectiveUrl)) {
    return (
      <InViewAutoplayVideo
        src={src}
        onError={(e) => {
          if (!placeholder) return
          // video → обёртка InViewAutoplayVideo → ячейка карточки
          const wrapper = e.currentTarget.parentElement?.parentElement
          if (!wrapper) return
          const img = document.createElement('img')
          img.src = placeholder
          img.alt = alt
          img.loading = 'lazy'
          img.decoding = 'async'
          img.className = 'pointer-events-none absolute inset-0 h-full w-full object-cover'
          wrapper.replaceChildren(img)
        }}
      />
    )
  }

  return (
    <FallbackMediaImage
      src={src}
      alt={alt}
      fallbackSrc={placeholder}
      sizes={MASONRY_IMAGE_SIZES}
    />
  )
}
