import { useEffect, useRef, useState } from 'react'
import { Compass as CompassIcon } from 'lucide-react'
import { CARDINALS, DIRECTION_LABEL, headingToCardinal } from '../lib/orientation.js'
import { Alert, Button } from './ui.jsx'

const ANGLE = { north: 0, east: 90, south: 180, west: 270 }
const wedge = (deg) => {
  const a1 = ((deg - 40 - 90) * Math.PI) / 180, a2 = ((deg + 40 - 90) * Math.PI) / 180
  const R = 92, r = 40
  const p = (a, rad) => `${(100 + rad * Math.cos(a)).toFixed(1)} ${(100 + rad * Math.sin(a)).toFixed(1)}`
  return `M ${p(a1, r)} L ${p(a1, R)} A ${R} ${R} 0 0 1 ${p(a2, R)} L ${p(a2, r)} A ${r} ${r} 0 0 0 ${p(a1, r)} Z`
}

/** Interactive compass: pick the direction photo 1 faces. Arrow keys cycle directions. */
export function CompassPicker({ value, onChange, heading }) {
  const onKey = (e) => {
    const i = CARDINALS.indexOf(value ?? 'north')
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); onChange(CARDINALS[(i + 1) % 4]) }
    if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); onChange(CARDINALS[(i + 3) % 4]) }
  }
  return (
    <div role="radiogroup" aria-label="Compass direction photo 1 faces" className="compass" onKeyDown={onKey}>
      <svg viewBox="0 0 200 200" width="100%" style={{ maxWidth: 280 }}>
        <circle cx="100" cy="100" r="96" fill="var(--surface)" stroke="var(--line-strong)" />
        {CARDINALS.map((d) => {
          const sel = value === d
          const a = ((ANGLE[d] - 90) * Math.PI) / 180
          return (
            <g key={d} role="radio" aria-checked={sel} aria-label={DIRECTION_LABEL[d]} tabIndex={sel || (!value && d === 'north') ? 0 : -1} onClick={() => onChange(d)} style={{ cursor: 'pointer' }}>
              <path d={wedge(ANGLE[d])} fill={sel ? 'var(--sage)' : 'var(--surface-2)'} stroke="var(--line-strong)" />
              <text x={100 + 66 * Math.cos(a)} y={100 + 66 * Math.sin(a)} textAnchor="middle" dominantBaseline="central" fontSize="22" fontFamily="var(--font-display)" fill={sel ? '#fff' : 'var(--ink)'} pointerEvents="none">{d[0].toUpperCase()}</text>
            </g>
          )
        })}
        {heading != null && (
          <g transform={`rotate(${heading} 100 100)`} pointerEvents="none"><path d="M100 22 L106 56 L100 50 L94 56 Z" fill="var(--danger)" /></g>
        )}
        <circle cx="100" cy="100" r="30" fill="var(--bg)" stroke="var(--line-strong)" />
        <text x="100" y="100" textAnchor="middle" dominantBaseline="central" fontSize="11" fill="var(--muted)" fontFamily="var(--font-body)">{value ? DIRECTION_LABEL[value] : 'Pick'}</text>
      </svg>
    </div>
  )
}

/** Live device-compass reader. Never assumes it works: browsers may lack the sensor, require HTTPS, or need permission. */
export function DeviceCompass({ onReading }) {
  const [state, setState] = useState('idle') // idle | asking | listening | unsupported | denied | nodata
  const [heading, setHeading] = useState(null)
  const handler = useRef(null)
  const timeout = useRef(null)
  const lastHeading = useRef(null)

  const stop = () => { if (handler.current) { window.removeEventListener('deviceorientationabsolute', handler.current, true); window.removeEventListener('deviceorientation', handler.current, true); handler.current = null }; clearTimeout(timeout.current) }
  useEffect(() => stop, [])

  const start = async () => {
    if (typeof window === 'undefined' || !('DeviceOrientationEvent' in window)) return setState('unsupported')
    setState('asking')
    try {
      if (typeof DeviceOrientationEvent.requestPermission === 'function') {
        const r = await DeviceOrientationEvent.requestPermission()
        if (r !== 'granted') return setState('denied')
      }
    } catch { return setState('denied') }
    handler.current = (e) => {
      let h = null
      if (typeof e.webkitCompassHeading === 'number') h = e.webkitCompassHeading // iOS: degrees clockwise from magnetic north
      else if (e.absolute && typeof e.alpha === 'number') h = (360 - e.alpha) % 360 // Android absolute event
      if (h == null || Number.isNaN(h)) return
      lastHeading.current = Math.round(h); setHeading(Math.round(h)); setState('listening'); clearTimeout(timeout.current)
    }
    window.addEventListener('deviceorientationabsolute', handler.current, true)
    window.addEventListener('deviceorientation', handler.current, true)
    timeout.current = setTimeout(() => { if (lastHeading.current == null) { stop(); setState('nodata') } }, 3500)
  }

  return (
    <div className="stack" style={{ '--gap': '.6rem' }}>
      {state === 'idle' && <Button variant="ghost" icon={<CompassIcon size={16} />} onClick={start}>Read my phone’s compass</Button>}
      {state === 'asking' && <p className="small muted">Waiting for permission and sensor data…</p>}
      {state === 'listening' && (
        <div className="card soft stack" style={{ '--gap': '.5rem' }}>
          <div className="row spread"><span>Live heading</span><strong>{heading}° · {DIRECTION_LABEL[headingToCardinal(heading)]}</strong></div>
          <p className="small muted" style={{ margin: 0 }}>Stand where you took photo 1, point the back of the phone the way the camera faced, keep it flat and away from metal and electronics, then lock the reading.</p>
          <div className="row"><Button variant="sage" size="sm" onClick={() => { stop(); setState('idle'); onReading(heading) }}>Lock this heading</Button><Button variant="ghost" size="sm" onClick={() => { stop(); setState('idle') }}>Cancel</Button></div>
        </div>
      )}
      {state === 'unsupported' && <Alert kind="warn" title="This device has no compass sensor available">Use the compass above and pick the direction yourself.</Alert>}
      {state === 'denied' && <Alert kind="warn" title="Compass permission was denied">You can pick the direction manually instead.</Alert>}
      {state === 'nodata' && <Alert kind="warn" title="No compass data was received">Phone compasses usually only work over HTTPS and on a handheld device. Pick the direction manually instead.</Alert>}
      {['unsupported', 'denied', 'nodata'].includes(state) && <Button variant="ghost" size="sm" onClick={() => setState('idle')}>Try again</Button>}
    </div>
  )
}
