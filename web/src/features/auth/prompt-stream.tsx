import { useEffect, useRef } from 'react'

/** Decorative-only motion layer for authentication screens. */
export function PromptStream() {
  const layerRef = useRef<HTMLDivElement>(null)
  const trackRef = useRef<SVGGElement>(null)
  const labelTrackRef = useRef<SVGGElement>(null)

  useEffect(() => {
    const layer = layerRef.current
    const track = trackRef.current
    const labelTrack = labelTrackRef.current
    if (!layer || !track || !labelTrack) return

    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    let frame = 0
    let start = performance.now()
    let pointerX = 0
    let pointerY = 0
    let currentX = 0
    let currentY = 0
    const setParallaxTarget = (event: PointerEvent) => {
      pointerX = (event.clientX / window.innerWidth - 0.5) * 4
      pointerY = (event.clientY / window.innerHeight - 0.5) * 3
    }
    const render = (now: number) => {
      currentX += (pointerX - currentX) * 0.035
      currentY += (pointerY - currentY) * 0.035
      layer.style.transform = `translate3d(${currentX.toFixed(2)}px, ${currentY.toFixed(2)}px, 0)`
      const elapsed = now - start
      const translate = `translate(${-(elapsed % 28000) * 1200 / 28000} 0)`
      track.setAttribute('transform', translate)
      labelTrack.setAttribute('transform', translate)
      frame = requestAnimationFrame(render)
    }
    const updateMotionPreference = () => {
      cancelAnimationFrame(frame)
      if (media.matches) {
        layer.style.transform = 'translate3d(0, 0, 0)'
        track.setAttribute('transform', 'translate(0 0)')
        labelTrack.setAttribute('transform', 'translate(0 0)')
      } else {
        start = performance.now()
        frame = requestAnimationFrame(render)
      }
    }
    window.addEventListener('pointermove', setParallaxTarget, { passive: true })
    media.addEventListener('change', updateMotionPreference)
    updateMotionPreference()
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('pointermove', setParallaxTarget)
      media.removeEventListener('change', updateMotionPreference)
    }
  }, [])

  return <div className="prompt-stream" aria-hidden="true" ref={layerRef}>
    <svg viewBox="0 0 1200 260" preserveAspectRatio="none" focusable="false">
      <defs>
        <path id="prompt-stream-path-a" d="M-100 145 C90 58 270 232 472 145 C674 58 858 232 1100 145" />
        <path id="prompt-stream-path-b" d="M1100 145 C1290 58 1470 232 1672 145 C1874 58 2058 232 2300 145" />
        <clipPath id="prompt-stream-label-clip"><rect x="40" y="0" width="1120" height="260" /></clipPath>
      </defs>
      <g ref={trackRef} className="prompt-stream-track">
        <use href="#prompt-stream-path-a" className="prompt-stream-ribbon" />
        <use href="#prompt-stream-path-b" className="prompt-stream-ribbon" />
      </g>
      <g clipPath="url(#prompt-stream-label-clip)">
        <g ref={labelTrackRef} className="prompt-stream-track">
          <text className="prompt-stream-label"><textPath href="#prompt-stream-path-a" startOffset="4%">Prompt → Version → Test → Compare → Approve → Deploy → Monitor → Prompt → Version → Test → Compare → Approve → Deploy → Monitor →</textPath></text>
          <text className="prompt-stream-label"><textPath href="#prompt-stream-path-b" startOffset="4%">Prompt → Version → Test → Compare → Approve → Deploy → Monitor → Prompt → Version → Test → Compare → Approve → Deploy → Monitor →</textPath></text>
        </g>
      </g>
    </svg>
  </div>
}
