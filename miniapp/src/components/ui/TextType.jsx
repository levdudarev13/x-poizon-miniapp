import { useEffect, useRef, useState, createElement, useMemo, useCallback } from 'react'
import gsap from 'gsap'
import './TextType.css'

export default function TextType({
  text,
  as: Component = 'div',
  typingSpeed = 50,
  initialDelay = 0,
  pauseDuration = 2000,
  deletingSpeed = 30,
  loop = true,
  className = '',
  showCursor = true,
  hideCursorWhileTyping = false,
  cursorCharacter = '|',
  cursorClassName = '',
  cursorBlinkDuration = 0.5,
  textColors = [],
  variableSpeed,
  onSentenceComplete,
  onTypingComplete,
  startOnVisible = false,
  reverseMode = false,
  ...props
}) {
  const [displayedText, setDisplayedText] = useState('')
  const [currentCharIndex, setCurrentCharIndex] = useState(0)
  const [isDeleting, setIsDeleting] = useState(false)
  const [currentTextIndex, setCurrentTextIndex] = useState(0)
  const [isVisible, setIsVisible] = useState(!startOnVisible)
  const cursorRef = useRef(null)
  const containerRef = useRef(null)
  const hasAnnouncedTypingCompleteRef = useRef(false)

  const textArray = useMemo(() => {
    const source = Array.isArray(text) ? text : [text]
    return source.map((item) => String(item ?? ''))
  }, [text])

  const getRandomSpeed = useCallback(() => {
    if (!Array.isArray(variableSpeed) || variableSpeed.length < 2) {
      return typingSpeed
    }

    const [min, max] = variableSpeed
    return Math.random() * (max - min) + min
  }, [typingSpeed, variableSpeed])

  const getCurrentTextColor = useCallback(() => {
    if (!Array.isArray(textColors) || textColors.length === 0) {
      return 'inherit'
    }

    return textColors[currentTextIndex % textColors.length]
  }, [currentTextIndex, textColors])

  useEffect(() => {
    setDisplayedText('')
    setCurrentCharIndex(0)
    setIsDeleting(false)
    setCurrentTextIndex(0)
    hasAnnouncedTypingCompleteRef.current = false
  }, [textArray, reverseMode])

  useEffect(() => {
    if (!startOnVisible || !containerRef.current) return undefined

    if (typeof window.IntersectionObserver !== 'function') {
      setIsVisible(true)
      return undefined
    }

    try {
      const observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              setIsVisible(true)
            }
          })
        },
        { threshold: 0.1 },
      )

      observer.observe(containerRef.current)
      return () => observer.disconnect()
    } catch (error) {
      console.warn('TextType observer disabled:', error)
      setIsVisible(true)
      return undefined
    }
  }, [startOnVisible])

  useEffect(() => {
    const cursorNode = cursorRef.current
    if (!showCursor || !cursorNode) return undefined

    try {
      gsap.killTweensOf(cursorNode)
      gsap.set(cursorNode, { opacity: 1 })

      const tween = gsap.to(cursorNode, {
        opacity: 0,
        duration: cursorBlinkDuration,
        repeat: -1,
        yoyo: true,
        ease: 'power2.inOut',
      })

      return () => {
        tween.kill()
        gsap.killTweensOf(cursorNode)
      }
    } catch (error) {
      console.warn('TextType cursor animation disabled:', error)
      return undefined
    }
  }, [showCursor, cursorBlinkDuration])

  useEffect(() => {
    if (!isVisible || textArray.length === 0) return undefined

    let timeoutId
    const currentText = textArray[currentTextIndex] || ''
    const processedText = reverseMode ? currentText.split('').reverse().join('') : currentText

    const executeTypingAnimation = () => {
      if (isDeleting) {
        if (displayedText === '') {
          if (onSentenceComplete) {
            onSentenceComplete(textArray[currentTextIndex], currentTextIndex)
          }

          if (currentTextIndex === textArray.length - 1 && !loop) {
            return
          }

          timeoutId = window.setTimeout(() => {
            setIsDeleting(false)
            setCurrentTextIndex((prev) => (prev + 1) % textArray.length)
            setCurrentCharIndex(0)
          }, pauseDuration)
        } else {
          timeoutId = window.setTimeout(() => {
            setDisplayedText((prev) => prev.slice(0, -1))
          }, deletingSpeed)
        }

        return
      }

      if (currentCharIndex < processedText.length) {
        timeoutId = window.setTimeout(() => {
          setDisplayedText((prev) => prev + processedText[currentCharIndex])
          setCurrentCharIndex((prev) => prev + 1)
        }, variableSpeed ? getRandomSpeed() : typingSpeed)

        return
      }

      if (textArray.length > 1 || loop) {
        timeoutId = window.setTimeout(() => {
          setIsDeleting(true)
        }, pauseDuration)
      }
    }

    if (currentCharIndex === 0 && !isDeleting && displayedText === '') {
      timeoutId = window.setTimeout(executeTypingAnimation, initialDelay)
    } else {
      executeTypingAnimation()
    }

    return () => {
      window.clearTimeout(timeoutId)
    }
  }, [
    currentCharIndex,
    currentTextIndex,
    deletingSpeed,
    displayedText,
    getRandomSpeed,
    initialDelay,
    isDeleting,
    isVisible,
    loop,
    onSentenceComplete,
    pauseDuration,
    reverseMode,
    textArray,
    typingSpeed,
    variableSpeed,
  ])

  useEffect(() => {
    const currentText = textArray[currentTextIndex] || ''
    const processedText = reverseMode ? currentText.split('').reverse().join('') : currentText
    const isTypingComplete = !isDeleting && processedText.length > 0 && displayedText === processedText && currentCharIndex >= processedText.length

    if (!isTypingComplete) {
      hasAnnouncedTypingCompleteRef.current = false
      return
    }

    if (hasAnnouncedTypingCompleteRef.current) {
      return
    }

    hasAnnouncedTypingCompleteRef.current = true
    onTypingComplete?.(textArray[currentTextIndex], currentTextIndex)
  }, [currentCharIndex, currentTextIndex, displayedText, isDeleting, onTypingComplete, reverseMode, textArray])

  const currentText = textArray[currentTextIndex] || ''
  const shouldHideCursor = hideCursorWhileTyping && (currentCharIndex < currentText.length || isDeleting)

  return createElement(
    Component,
    {
      ref: containerRef,
      className: ['text-type', className].filter(Boolean).join(' '),
      ...props,
    },
    <span className="text-type__content" style={{ color: getCurrentTextColor() }}>
      {displayedText}
    </span>,
    showCursor ? (
      <span
        ref={cursorRef}
        className={['text-type__cursor', cursorClassName, shouldHideCursor ? 'text-type__cursor--hidden' : ''].filter(Boolean).join(' ')}
      >
        {cursorCharacter}
      </span>
    ) : null,
  )
}
