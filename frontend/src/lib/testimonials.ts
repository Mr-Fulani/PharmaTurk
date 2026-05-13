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
