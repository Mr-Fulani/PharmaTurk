import { buildProductUrl } from './urls'

export interface TestimonialMedia {
  id: number
  media_type: 'image' | 'video' | 'video_file'
  image_url: string | null
  video_url: string | null
  video_file_url: string | null
  order: number
}

export interface Testimonial {
  id: number
  author_name: string
  author_avatar_url: string | null
  text: string
  rating: number | null
  media: TestimonialMedia[]
  created_at: string
  user_id?: number | null
  user_username?: string | null
}

export function buildTestimonialUrl(id: number | string): string {
  return `/testimonials/${id}`
}

export interface ReviewFeedItem {
  uid: string
  id: number
  source_type: 'testimonial' | 'product_review'
  review_type: 'platform' | 'product' | 'service'
  author_name: string
  author_avatar_url: string | null
  text: string
  rating: number | null
  media: TestimonialMedia[]
  created_at: string
  user_id?: number | null
  user_username?: string | null
  product_type: string | null
  product_slug: string | null
  product_name: string | null
  subject_image_url: string | null
  homepage_priority: number
}

export function buildReviewDetailUrl(review: ReviewFeedItem): string {
  if (review.source_type === 'testimonial') {
    return buildTestimonialUrl(review.id)
  }
  if (review.product_type && review.product_slug) {
    return `${buildProductUrl(review.product_type, review.product_slug)}#product-reviews`
  }
  return '/testimonials'
}

export function buildReviewAuthorUrl(review: ReviewFeedItem): string | null {
  if (!review.user_username) return null
  const base = `/user/${encodeURIComponent(review.user_username)}`
  return review.source_type === 'testimonial' ? `${base}?testimonial_id=${review.id}` : base
}
