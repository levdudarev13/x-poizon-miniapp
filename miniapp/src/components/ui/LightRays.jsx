import { useEffect, useRef, useState } from 'react'
import { Renderer, Program, Triangle, Mesh } from 'ogl'
import './LightRays.css'

const DEFAULT_COLOR = '#15ffcc'

function clamp01(value) {
  return Math.max(0, Math.min(1, value))
}

function hexToRgb(hex) {
  const normalized = String(hex || '').trim()
  const match = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(normalized)
  return match
    ? [
      parseInt(match[1], 16) / 255,
      parseInt(match[2], 16) / 255,
      parseInt(match[3], 16) / 255,
    ]
    : [1, 1, 1]
}

function getAnchorAndDir(origin, width, height) {
  const outside = 0.2

  switch (origin) {
    case 'top-left':
      return { anchor: [0, -outside * height], dir: [0, 1] }
    case 'top-right':
      return { anchor: [width, -outside * height], dir: [0, 1] }
    case 'left':
      return { anchor: [-outside * width, 0.5 * height], dir: [1, 0] }
    case 'right':
      return { anchor: [(1 + outside) * width, 0.5 * height], dir: [-1, 0] }
    case 'bottom-left':
      return { anchor: [0, (1 + outside) * height], dir: [0, -1] }
    case 'bottom-center':
      return { anchor: [0.5 * width, (1 + outside) * height], dir: [0, -1] }
    case 'bottom-right':
      return { anchor: [width, (1 + outside) * height], dir: [0, -1] }
    default:
      return { anchor: [0.5 * width, -outside * height], dir: [0, 1] }
  }
}

function supportsIntersectionObserver() {
  return typeof window !== 'undefined' && typeof window.IntersectionObserver === 'function'
}

function supportsWebGL() {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return false
  }

  try {
    const canvas = document.createElement('canvas')
    return Boolean(
      window.WebGLRenderingContext &&
      (canvas.getContext('webgl') || canvas.getContext('experimental-webgl')),
    )
  } catch {
    return false
  }
}

export default function LightRays({
  raysOrigin = 'top-center',
  raysColor = DEFAULT_COLOR,
  raysSpeed = 1,
  lightSpread = 1,
  rayLength = 2,
  pulsating = false,
  fadeDistance = 1,
  saturation = 1,
  followMouse = true,
  mouseInfluence = 0.1,
  noiseAmount = 0,
  distortion = 0,
  className = '',
}) {
  const containerRef = useRef(null)
  const uniformsRef = useRef(null)
  const rendererRef = useRef(null)
  const meshRef = useRef(null)
  const animationFrameRef = useRef(null)
  const cleanupRef = useRef(null)
  const observerRef = useRef(null)
  const mouseRef = useRef({ x: 0.5, y: 0.5 })
  const smoothMouseRef = useRef({ x: 0.5, y: 0.5 })
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    const element = containerRef.current
    if (!element) return undefined

    if (!supportsIntersectionObserver()) {
      setIsVisible(true)
      return undefined
    }

    try {
      observerRef.current = new IntersectionObserver(
        ([entry]) => {
          setIsVisible(Boolean(entry?.isIntersecting))
        },
        { threshold: 0.1 },
      )

      observerRef.current.observe(element)
    } catch (error) {
      console.warn('LightRays observer disabled:', error)
      setIsVisible(true)
    }

    return () => {
      observerRef.current?.disconnect()
      observerRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!isVisible || !containerRef.current) return undefined

    cleanupRef.current?.()
    cleanupRef.current = null

    let cancelled = false

    const initialize = async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10))
      if (cancelled || !containerRef.current) return

      if (!supportsWebGL()) {
        return
      }

      try {
        const renderer = new Renderer({
          dpr: Math.min(window.devicePixelRatio || 1, 2),
          alpha: true,
        })
        rendererRef.current = renderer

        const { gl } = renderer
        gl.canvas.style.width = '100%'
        gl.canvas.style.height = '100%'
        gl.canvas.style.display = 'block'

        while (containerRef.current.firstChild) {
          containerRef.current.removeChild(containerRef.current.firstChild)
        }
        containerRef.current.appendChild(gl.canvas)

        const vertex = `
        attribute vec2 position;
        varying vec2 vUv;

        void main() {
          vUv = position * 0.5 + 0.5;
          gl_Position = vec4(position, 0.0, 1.0);
        }
      `

        const fragment = `
        precision highp float;

        uniform float iTime;
        uniform vec2 iResolution;
        uniform vec2 rayPos;
        uniform vec2 rayDir;
        uniform vec3 raysColor;
        uniform float raysSpeed;
        uniform float lightSpread;
        uniform float rayLength;
        uniform float pulsating;
        uniform float fadeDistance;
        uniform float saturation;
        uniform vec2 mousePos;
        uniform float mouseInfluence;
        uniform float noiseAmount;
        uniform float distortion;

        varying vec2 vUv;

        float noise(vec2 st) {
          return fract(sin(dot(st.xy, vec2(12.9898, 78.233))) * 43758.5453123);
        }

        float rayStrength(
          vec2 raySource,
          vec2 rayRefDirection,
          vec2 coord,
          float seedA,
          float seedB,
          float speed
        ) {
          vec2 sourceToCoord = coord - raySource;
          vec2 dirNorm = normalize(sourceToCoord);
          float cosAngle = dot(dirNorm, rayRefDirection);

          float distortedAngle = cosAngle +
            distortion * sin(iTime * 2.0 + length(sourceToCoord) * 0.01) * 0.2;

          float spreadFactor = pow(max(distortedAngle, 0.0), 1.0 / max(lightSpread, 0.001));

          float distance = length(sourceToCoord);
          float maxDistance = iResolution.x * rayLength;
          float lengthFalloff = clamp((maxDistance - distance) / maxDistance, 0.0, 1.0);
          float fadeFalloff = clamp(
            (iResolution.x * fadeDistance - distance) / (iResolution.x * fadeDistance),
            0.5,
            1.0
          );
          float pulse = pulsating > 0.5 ? (0.8 + 0.2 * sin(iTime * speed * 3.0)) : 1.0;

          float baseStrength = clamp(
            (0.45 + 0.15 * sin(distortedAngle * seedA + iTime * speed)) +
            (0.3 + 0.2 * cos(-distortedAngle * seedB + iTime * speed)),
            0.0,
            1.0
          );

          return baseStrength * lengthFalloff * fadeFalloff * spreadFactor * pulse;
        }

        void mainImage(out vec4 fragColor, in vec2 fragCoord) {
          vec2 coord = vec2(fragCoord.x, iResolution.y - fragCoord.y);
          vec2 finalRayDir = rayDir;

          if (mouseInfluence > 0.0) {
            vec2 mouseScreenPos = mousePos * iResolution.xy;
            vec2 mouseDirection = normalize(mouseScreenPos - rayPos);
            finalRayDir = normalize(mix(rayDir, mouseDirection, mouseInfluence));
          }

          vec4 rays1 = vec4(1.0) * rayStrength(
            rayPos,
            finalRayDir,
            coord,
            36.2214,
            21.11349,
            1.5 * raysSpeed
          );

          vec4 rays2 = vec4(1.0) * rayStrength(
            rayPos,
            finalRayDir,
            coord,
            22.3991,
            18.0234,
            1.1 * raysSpeed
          );

          fragColor = rays1 * 0.5 + rays2 * 0.4;

          if (noiseAmount > 0.0) {
            float n = noise(coord * 0.01 + iTime * 0.1);
            fragColor.rgb *= (1.0 - noiseAmount + noiseAmount * n);
          }

          float brightness = 1.0 - (coord.y / iResolution.y);
          fragColor.r *= 0.1 + brightness * 0.8;
          fragColor.g *= 0.3 + brightness * 0.6;
          fragColor.b *= 0.5 + brightness * 0.5;

          if (saturation != 1.0) {
            float gray = dot(fragColor.rgb, vec3(0.299, 0.587, 0.114));
            fragColor.rgb = mix(vec3(gray), fragColor.rgb, saturation);
          }

          fragColor.rgb *= raysColor;
        }

        void main() {
          vec4 color;
          mainImage(color, gl_FragCoord.xy);
          gl_FragColor = color;
        }
      `

        const uniforms = {
          iTime: { value: 0 },
          iResolution: { value: [1, 1] },
          rayPos: { value: [0, 0] },
          rayDir: { value: [0, 1] },
          raysColor: { value: hexToRgb(raysColor) },
          raysSpeed: { value: raysSpeed },
          lightSpread: { value: lightSpread },
          rayLength: { value: rayLength },
          pulsating: { value: pulsating ? 1 : 0 },
          fadeDistance: { value: fadeDistance },
          saturation: { value: saturation },
          mousePos: { value: [0.5, 0.5] },
          mouseInfluence: { value: mouseInfluence },
          noiseAmount: { value: noiseAmount },
          distortion: { value: distortion },
        }
        uniformsRef.current = uniforms

        const geometry = new Triangle(gl)
        const program = new Program(gl, {
          vertex,
          fragment,
          uniforms,
        })
        const mesh = new Mesh(gl, { geometry, program })
        meshRef.current = mesh

        const updatePlacement = () => {
          if (!containerRef.current || !rendererRef.current || !uniformsRef.current) return

          rendererRef.current.dpr = Math.min(window.devicePixelRatio || 1, 2)

          const { clientWidth, clientHeight } = containerRef.current
          rendererRef.current.setSize(clientWidth, clientHeight)

          const width = clientWidth * rendererRef.current.dpr
          const height = clientHeight * rendererRef.current.dpr
          const { anchor, dir } = getAnchorAndDir(raysOrigin, width, height)

          uniformsRef.current.iResolution.value = [width, height]
          uniformsRef.current.rayPos.value = anchor
          uniformsRef.current.rayDir.value = dir
        }

        const renderFrame = (time) => {
          if (!rendererRef.current || !uniformsRef.current || !meshRef.current) return

          uniformsRef.current.iTime.value = time * 0.001

          if (followMouse && mouseInfluence > 0) {
            const smoothing = 0.92
            smoothMouseRef.current.x = smoothMouseRef.current.x * smoothing + mouseRef.current.x * (1 - smoothing)
            smoothMouseRef.current.y = smoothMouseRef.current.y * smoothing + mouseRef.current.y * (1 - smoothing)
            uniformsRef.current.mousePos.value = [smoothMouseRef.current.x, smoothMouseRef.current.y]
          }

          try {
            rendererRef.current.render({ scene: meshRef.current })
            animationFrameRef.current = window.requestAnimationFrame(renderFrame)
          } catch (error) {
            console.warn('LightRays render error:', error)
          }
        }

        window.addEventListener('resize', updatePlacement)
        updatePlacement()
        animationFrameRef.current = window.requestAnimationFrame(renderFrame)

        cleanupRef.current = () => {
          if (animationFrameRef.current) {
            window.cancelAnimationFrame(animationFrameRef.current)
            animationFrameRef.current = null
          }

          window.removeEventListener('resize', updatePlacement)

          if (rendererRef.current?.gl) {
            const canvas = rendererRef.current.gl.canvas
            const loseContext = rendererRef.current.gl.getExtension('WEBGL_lose_context')
            loseContext?.loseContext()

            if (canvas?.parentNode) {
              canvas.parentNode.removeChild(canvas)
            }
          }

          rendererRef.current = null
          uniformsRef.current = null
          meshRef.current = null
        }
      } catch (error) {
        console.warn('LightRays disabled:', error)
        cleanupRef.current?.()
        cleanupRef.current = null
      }
    }

    initialize()

    return () => {
      cancelled = true
      cleanupRef.current?.()
      cleanupRef.current = null
    }
  }, [
    distortion,
    fadeDistance,
    followMouse,
    isVisible,
    lightSpread,
    mouseInfluence,
    noiseAmount,
    pulsating,
    rayLength,
    raysColor,
    raysOrigin,
    raysSpeed,
    saturation,
  ])

  useEffect(() => {
    if (!uniformsRef.current || !containerRef.current || !rendererRef.current) return

    const width = containerRef.current.clientWidth * rendererRef.current.dpr
    const height = containerRef.current.clientHeight * rendererRef.current.dpr
    const { anchor, dir } = getAnchorAndDir(raysOrigin, width, height)

    uniformsRef.current.raysColor.value = hexToRgb(raysColor)
    uniformsRef.current.raysSpeed.value = raysSpeed
    uniformsRef.current.lightSpread.value = lightSpread
    uniformsRef.current.rayLength.value = rayLength
    uniformsRef.current.pulsating.value = pulsating ? 1 : 0
    uniformsRef.current.fadeDistance.value = fadeDistance
    uniformsRef.current.saturation.value = saturation
    uniformsRef.current.mouseInfluence.value = mouseInfluence
    uniformsRef.current.noiseAmount.value = noiseAmount
    uniformsRef.current.distortion.value = distortion
    uniformsRef.current.rayPos.value = anchor
    uniformsRef.current.rayDir.value = dir
  }, [
    distortion,
    fadeDistance,
    lightSpread,
    mouseInfluence,
    noiseAmount,
    pulsating,
    rayLength,
    raysColor,
    raysOrigin,
    raysSpeed,
    saturation,
  ])

  useEffect(() => {
    if (!followMouse) return undefined

    const updatePointer = (clientX, clientY) => {
      if (!containerRef.current) return

      const rect = containerRef.current.getBoundingClientRect()
      if (!rect.width || !rect.height) return

      mouseRef.current = {
        x: clamp01((clientX - rect.left) / rect.width),
        y: clamp01((clientY - rect.top) / rect.height),
      }
    }

    const handlePointerMove = (event) => {
      updatePointer(event.clientX, event.clientY)
    }

    window.addEventListener('pointermove', handlePointerMove, { passive: true })

    return () => {
      window.removeEventListener('pointermove', handlePointerMove)
    }
  }, [followMouse])

  return <div ref={containerRef} className={`light-rays-container ${className}`.trim()} aria-hidden="true" />
}
