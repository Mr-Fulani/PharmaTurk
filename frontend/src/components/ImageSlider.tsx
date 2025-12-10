import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/router'
import styles from './ImageSlider.module.css'
import { resolveMediaUrl } from '../lib/media'

interface SliderItem {
  id: number
  imageUrl: string
  title: string
  description: string
  linkUrl?: string
  linkText?: string
}

interface ImageSliderProps {
  items: SliderItem[]
  className?: string
  autoPlayInterval?: number // в миллисекундах, 0 для отключения
}

export default function ImageSlider({ 
  items, 
  className = '',
  autoPlayInterval = 10000 
}: ImageSliderProps) {
  const router = useRouter()
  const [displayItems, setDisplayItems] = useState<SliderItem[]>(items)
  const slideRef = useRef<HTMLDivElement>(null)

  // Инициализация порядка элементов
  useEffect(() => {
    if (items.length > 0) {
      setDisplayItems(items)
    }
  }, [items])

  // Автоматическая смена слайдов
  useEffect(() => {
    if (autoPlayInterval <= 0 || items.length <= 1) return

    const interval = setInterval(() => {
      handleNext()
    }, autoPlayInterval)

    return () => clearInterval(interval)
  }, [autoPlayInterval, items.length])

  const handleNext = () => {
    if (items.length <= 1) return
    setDisplayItems((prev) => {
      const newItems = [...prev]
      const firstItem = newItems.shift()
      if (firstItem) {
        newItems.push(firstItem)
      }
      return newItems
    })
  }

  const handlePrev = () => {
    if (items.length <= 1) return
    setDisplayItems((prev) => {
      const newItems = [...prev]
      const lastItem = newItems.pop()
      if (lastItem) {
        newItems.unshift(lastItem)
      }
      return newItems
    })
  }

  const handleItemClick = (item: SliderItem) => {
    if (!item.linkUrl) return
    
    const isExternal = /^https?:\/\//.test(item.linkUrl)
    if (isExternal) {
      window.open(item.linkUrl, '_blank', 'noopener, noreferrer')
    } else {
      router.push(item.linkUrl)
    }
  }

  if (items.length === 0) {
    return null
  }

  return (
    <div className={`${styles.container} ${className}`}>
      <div ref={slideRef} className={styles.slide}>
        {displayItems.map((item, index) => (
          <div
            key={item.id}
            className={styles.item}
            style={{
              backgroundImage: `url(${resolveMediaUrl(item.imageUrl)})`,
            }}
          >
            <div className={styles.content}>
              <div className={styles.name}>{item.title}</div>
              <div className={styles.des}>{item.description}</div>
              {item.linkText && item.linkUrl && (
                <button 
                  onClick={() => handleItemClick(item)}
                  className={styles.button}
                >
                  {item.linkText}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {items.length > 1 && (
        <div className={styles.buttonContainer}>
          <button 
            className={styles.navButton} 
            onClick={handlePrev}
            aria-label="Предыдущий слайд"
          >
            <svg className={styles.icon} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <button 
            className={styles.navButton} 
            onClick={handleNext}
            aria-label="Следующий слайд"
          >
            <svg className={styles.icon} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>
      )}
    </div>
  )
}

