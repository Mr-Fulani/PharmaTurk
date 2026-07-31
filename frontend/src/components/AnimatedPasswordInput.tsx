import {
  InputHTMLAttributes,
  useEffect,
  useId,
  useRef,
  useState,
} from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import styles from './AnimatedPasswordInput.module.css'

type AnimatedPasswordInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & {
  inputClassName?: string
  showLabel?: string
  hideLabel?: string
}

const OPEN_LID = 'M1 12C1 12 5 4 12 4C19 4 23 12 23 12'
const CLOSED_LID = 'M1 12C1 12 5 20 12 20C19 20 23 12 23 12'
const OPEN_MASK = 'M1 12C1 12 5 4 12 4C19 4 23 12 23 12V20H1V12Z'
const CLOSED_MASK = 'M1 12C1 12 5 20 12 20C19 20 23 12 23 12V20H1V12Z'
const SCRAMBLE_CHARACTERS =
  'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789~<>?/;:[]{}+_*&%$#@!'
const SCRAMBLE_DURATION = 650

export default function AnimatedPasswordInput({
  inputClassName = '',
  showLabel = 'Показать пароль',
  hideLabel = 'Скрыть пароль',
  disabled,
  value,
  readOnly,
  ...inputProps
}: AnimatedPasswordInputProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const toggleRef = useRef<HTMLButtonElement>(null)
  const eyeGroupRef = useRef<SVGGElement>(null)
  const blinkTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const revealTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pointerResetTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pointerFrameRef = useRef<number | null>(null)
  const animationFrameRef = useRef<number | null>(null)
  const [revealed, setRevealed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [blinking, setBlinking] = useState(false)
  const [scrambledValue, setScrambledValue] = useState<string | null>(null)
  const prefersReducedMotion = useReducedMotion()
  const rawId = useId()
  const maskId = `password-eye-${rawId.replace(/:/g, '')}`
  const eyeClosed = revealed || busy || blinking

  useEffect(() => {
    if (revealed || busy || prefersReducedMotion) {
      setBlinking(false)
      return
    }

    const scheduleBlink = () => {
      const delay = 2200 + Math.random() * 4800
      blinkTimeoutRef.current = setTimeout(() => {
        setBlinking(true)
        blinkTimeoutRef.current = setTimeout(() => {
          setBlinking(false)
          scheduleBlink()
        }, 150)
      }, delay)
    }

    scheduleBlink()
    return () => {
      if (blinkTimeoutRef.current) clearTimeout(blinkTimeoutRef.current)
    }
  }, [busy, prefersReducedMotion, revealed])

  useEffect(() => {
    const resetEyePosition = () => {
      eyeGroupRef.current?.setAttribute('transform', 'translate(0 0)')
    }

    if (eyeClosed || prefersReducedMotion) {
      resetEyePosition()
      return
    }

    const handlePointerMove = (event: PointerEvent) => {
      if (pointerFrameRef.current !== null) cancelAnimationFrame(pointerFrameRef.current)
      pointerFrameRef.current = requestAnimationFrame(() => {
        pointerFrameRef.current = null
        const bounds = toggleRef.current?.getBoundingClientRect()
        const eye = eyeGroupRef.current
        if (!bounds || !eye) return

        const centerX = bounds.left + bounds.width / 2
        const centerY = bounds.top + bounds.height / 2
        const deltaX = event.clientX - centerX
        const deltaY = event.clientY - centerY
        const distance = Math.max(1, Math.hypot(deltaX, deltaY))
        const strength = Math.min(1, distance / 90)

        const x = (deltaX / distance) * 2.4 * strength
        const y = (deltaY / distance) * 2.4 * strength
        eye.setAttribute('transform', `translate(${x.toFixed(2)} ${y.toFixed(2)})`)
      })

      if (pointerResetTimeoutRef.current) clearTimeout(pointerResetTimeoutRef.current)
      pointerResetTimeoutRef.current = setTimeout(resetEyePosition, 2000)
    }

    window.addEventListener('pointermove', handlePointerMove, { passive: true })
    return () => {
      window.removeEventListener('pointermove', handlePointerMove)
      if (pointerFrameRef.current !== null) cancelAnimationFrame(pointerFrameRef.current)
      if (pointerResetTimeoutRef.current) clearTimeout(pointerResetTimeoutRef.current)
      pointerFrameRef.current = null
    }
  }, [eyeClosed, prefersReducedMotion])

  useEffect(() => {
    return () => {
      if (blinkTimeoutRef.current) clearTimeout(blinkTimeoutRef.current)
      if (revealTimeoutRef.current) clearTimeout(revealTimeoutRef.current)
      if (pointerResetTimeoutRef.current) clearTimeout(pointerResetTimeoutRef.current)
      if (pointerFrameRef.current !== null) cancelAnimationFrame(pointerFrameRef.current)
      if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current)
    }
  }, [])

  const restoreCaret = (start: number | null, end: number | null) => {
    requestAnimationFrame(() => {
      const input = inputRef.current
      if (!input) return
      input.focus({ preventScroll: true })
      if (start !== null && end !== null) input.setSelectionRange(start, end)
    })
  }

  const runScramble = (
    passwordValue: string,
    direction: 'reveal' | 'hide',
    onComplete: () => void
  ) => {
    if (!passwordValue) {
      onComplete()
      return
    }

    const startedAt = performance.now()
    const lastIndex = Math.max(1, passwordValue.length - 1)

    const drawFrame = (now: number) => {
      const progress = Math.min(1, (now - startedAt) / SCRAMBLE_DURATION)
      const nextValue = Array.from(passwordValue, (character, index) => {
        const phaseStart = (index / lastIndex) * 0.55
        const localProgress = (progress - phaseStart) / 0.45

        if (localProgress <= 0) return direction === 'reveal' ? '•' : character
        if (localProgress >= 1) return direction === 'reveal' ? character : '•'
        if (character === ' ') return ' '
        return SCRAMBLE_CHARACTERS[Math.floor(Math.random() * SCRAMBLE_CHARACTERS.length)]
      }).join('')

      setScrambledValue(nextValue)
      if (progress < 1) {
        animationFrameRef.current = requestAnimationFrame(drawFrame)
        return
      }

      animationFrameRef.current = null
      onComplete()
    }

    animationFrameRef.current = requestAnimationFrame(drawFrame)
  }

  const toggleVisibility = () => {
    if (busy || disabled) return

    const input = inputRef.current
    const selectionStart = input?.selectionStart ?? null
    const selectionEnd = input?.selectionEnd ?? null
    const passwordValue = String(value ?? input?.value ?? '')

    if (prefersReducedMotion) {
      setRevealed((current) => !current)
      restoreCaret(selectionStart, selectionEnd)
      return
    }

    setBusy(true)
    if (revealed) {
      runScramble(passwordValue, 'hide', () => {
        setRevealed(false)
        setScrambledValue(null)
        setBusy(false)
        restoreCaret(selectionStart, selectionEnd)
      })
      return
    }

    revealTimeoutRef.current = setTimeout(() => {
      setRevealed(true)
      runScramble(passwordValue, 'reveal', () => {
        setScrambledValue(null)
        setBusy(false)
        restoreCaret(selectionStart, selectionEnd)
      })
    }, 125)
  }

  const label = revealed ? hideLabel : showLabel
  const animationDuration = prefersReducedMotion ? 0 : 0.14

  return (
    <div className={styles.wrapper}>
      <input
        {...inputProps}
        ref={inputRef}
        type={revealed ? 'text' : 'password'}
        disabled={disabled}
        readOnly={readOnly || busy}
        value={scrambledValue ?? value}
        className={`${styles.input} ${inputClassName}`.trim()}
      />
      <button
        ref={toggleRef}
        type="button"
        className={styles.toggle}
        onClick={toggleVisibility}
        onMouseDown={(event) => event.preventDefault()}
        disabled={disabled}
        aria-label={label}
        aria-pressed={revealed}
        title={label}
      >
        <svg
          className={styles.icon}
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <defs>
            <mask id={maskId}>
              <motion.path
                d={OPEN_MASK}
                animate={{ d: eyeClosed ? CLOSED_MASK : OPEN_MASK }}
                transition={{ duration: animationDuration, ease: 'easeInOut' }}
                fill="white"
              />
            </mask>
          </defs>
          <motion.path
            d={OPEN_LID}
            animate={{ d: eyeClosed ? CLOSED_LID : OPEN_LID }}
            transition={{ duration: animationDuration, ease: 'easeInOut' }}
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d={CLOSED_LID}
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <g
            ref={eyeGroupRef}
            mask={`url(#${maskId})`}
            transform="translate(0 0)"
          >
            <circle cy="12" cx="12" r="4" fill="currentColor" />
            <circle className={styles.glint} cy="11" cx="13" r="1" />
          </g>
        </svg>
      </button>
    </div>
  )
}
